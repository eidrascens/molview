/* Mol* rendering/analysis layer. All user-facing controls live in GTK. */
// The Mol* package API is intentionally used through documented public modules.

import { PluginContext } from 'molstar/lib/mol-plugin/context';
import { PluginCommands } from 'molstar/lib/mol-plugin/commands';
import { DefaultPluginSpec } from 'molstar/lib/mol-plugin/spec';
import { Color } from 'molstar/lib/mol-util/color';
import { Unit } from 'molstar/lib/mol-model/structure';
import { AA_ONE, detectStructureFormat, parseMmCifSequences, parsePdbSequences, sequenceQuality, sourceLooksLikeCif, type ChainSummary } from './sequence-parser';

type PublicComponent = {
    id: string;
    label: string;
    atomCount: number;
    hidden: boolean;
    category: string;
};

type ComponentGroup = {
    id: string;
    key: string;
    label: string;
    refs: any[];
};

type ProteinViewerApi = {
    loadStructureText(text: string, name: string): Promise<void>;
    setBackground(mode: 'transparent' | 'light' | 'dark'): void;
    setRepresentation(name: string): Promise<void>;
    resetCamera(): void;
    orientAxes(): Promise<void>;
    resetAxes(): Promise<void>;
    setCameraMode(mode: 'perspective' | 'orthographic'): void;
    setRenderSetting(setting: 'occlusion' | 'shadow' | 'outline', enabled: boolean): void;
    setIllumination(enabled: boolean): void;
    selectComponent(componentId: string): Promise<void>;
    toggleComponentVisibility(componentId: string): Promise<void>;
    removeComponent(componentId: string): Promise<void>;
};

declare global {
    interface Window { proteinViewer?: ProteinViewerApi; }
}

const FRONTEND_BUILD = 'titlebar-render-settings-2026-10-20-r2';

const PRESETS: Record<string, string> = {
    cartoon: 'polymer-cartoon',
    'cartoon-ligands': 'polymer-and-ligand',
    atoms: 'atomic-detail',
    surface: 'molecular-surface'
};

const canvas = document.getElementById('molstar-canvas') as HTMLCanvasElement;
const parent = document.getElementById('molstar-parent') as HTMLDivElement;
const fatal = document.getElementById('fatal') as HTMLDivElement;

let plugin: PluginContext | undefined;
let currentStructure: any;
let currentStructureRef: any;
let currentName = '';
let currentSourceText = '';
let currentFormat: 'pdb' | 'mmcif' = 'pdb';
let currentComponents = new Map<string, ComponentGroup>();

function emit(type: string, payload: Record<string, unknown> = {}): void {
    try {
        const handler = (window as any).webkit?.messageHandlers?.native;
        if (handler) handler.postMessage(JSON.stringify({ type, ...payload }));
    } catch (_error) {
        // Avoid recursively calling the console bridge if WebKit's native
        // message handler is unavailable during page shutdown.
    }
}

function errorText(error: unknown): { message: string; stack: string } {
    if (error instanceof Error) return { message: error.message, stack: error.stack ?? '' };
    return { message: String(error), stack: '' };
}

// Forward uncaught frontend errors and console errors to the Python log file.
// These messages are diagnostic only; the native UI remains the sole UI layer.
for (const level of ['error', 'warn'] as const) {
    const original = console[level].bind(console);
    console[level] = (...args: unknown[]) => {
        original(...args);
        emit(level === 'error' ? 'console-error' : 'console-warning', {
            message: args.map(arg => arg instanceof Error ? `${arg.message}\n${arg.stack ?? ''}` : String(arg)).join(' ')
        });
    };
}
window.addEventListener('error', event => {
    const detail = errorText(event.error ?? event.message);
    emit('js-error', {
        message: detail.message, stack: detail.stack,
        source: event.filename, line: event.lineno, column: event.colno
    });
});
window.addEventListener('unhandledrejection', event => {
    const detail = errorText(event.reason);
    emit('unhandled-rejection', detail);
});

function showFatal(message: string): void {
    fatal.textContent = message;
    fatal.style.display = 'block';
    emit('error', { message });
}

function safeValue(column: any, index: number): any {
    try {
        if (!column || typeof column.value !== 'function') return null;
        const value = column.value(index);
        if (value === undefined || value === null || value === '.' || value === '?') return null;
        return value;
    } catch {
        return null;
    }
}

function normalizedText(value: unknown, fallback = ''): string {
    if (value === null || value === undefined) return fallback;
    const result = String(value).trim();
    return result === '.' || result === '?' ? fallback : result;
}

function firstText(values: unknown[], fallback = ''): string {
    for (const value of values) {
        const text = normalizedText(value, '');
        if (text && text.toUpperCase() !== 'UNK') return text;
    }
    return fallback;
}

function collectPolymerSequences(structure: any): ChainSummary[] {
    // Mol*'s hierarchy sequence is a fallback. Some file/parser combinations
    // expose only X codes here, so source-text parsing is used first below.
    const summaries = new Map<string, ChainSummary>();
    for (const unit of structure.units ?? []) {
        if (!Unit.isAtomic(unit)) continue;
        const hierarchy = unit.model.atomicHierarchy;
        const chains = hierarchy.chains;
        const chainIndices = new Set<number>();
        for (let offset = 0; offset < unit.elements.length; offset++) {
            const atomIndex = unit.elements[offset];
            const chainIndex = hierarchy.chainAtomSegments.index[atomIndex];
            if (Number.isInteger(chainIndex) && chainIndex >= 0) chainIndices.add(chainIndex);
        }
        for (const chainIndex of chainIndices) {
            let entityIndex: number;
            try { entityIndex = hierarchy.index.getEntityFromChain(chainIndex); }
            catch { continue; }
            // byEntityKey is keyed by entity identifier (e.g. '1'), not by the
            // numeric row index returned by getEntityFromChain. Using the row
            // index here silently misses the actual sequence on many structures.
            const entityId = normalizedText(safeValue(hierarchy.entities?.id, entityIndex), String(entityIndex));
            const sequenceByKey = unit.model.sequence?.byEntityKey;
            const modelSequence = sequenceByKey?.[entityId]?.sequence
                ?? sequenceByKey?.[String(entityIndex)]?.sequence
                ?? sequenceByKey?.[entityId]
                ?? sequenceByKey?.[String(entityIndex)];
            if (!modelSequence?.compId || !modelSequence?.code) continue;
            if (modelSequence.kind && modelSequence.kind !== 'protein') continue;
            const authChain = firstText([safeValue(chains.auth_asym_id, chainIndex)]);
            const labelChain = firstText([safeValue(chains.label_asym_id, chainIndex)]);
            const id = authChain || labelChain || '(blank)';
            const letters: string[] = [];
            const rawLength = modelSequence.length ?? modelSequence.compId.rowCount ?? 0;
            const length = Number(typeof rawLength === 'function' ? rawLength.call(modelSequence) : rawLength);
            for (let i = 0; i < (Number.isFinite(length) ? length : 0); i++) {
                const compId = normalizedText(safeValue(modelSequence.compId, i), '').toUpperCase();
                const modelCode = normalizedText(safeValue(modelSequence.code, i), '').toUpperCase();
                const mappedLetter = AA_ONE[compId];
                letters.push(mappedLetter && mappedLetter !== 'X'
                    ? mappedLetter
                    : (modelCode.length === 1 && modelCode !== 'X' ? modelCode : mappedLetter ?? 'X'));
            }
            if (!letters.length) continue;
            const candidate = { id, sequence: letters.join(''), residueCount: letters.length };
            const current = summaries.get(id);
            if (!current || sequenceQuality(candidate.sequence) > sequenceQuality(current.sequence)) summaries.set(id, candidate);
        }
    }
    return [...summaries.values()].sort((a, b) => a.id.localeCompare(b.id));
}

function parseSourceSequences(text: string, format: 'pdb' | 'mmcif'): ChainSummary[] {
    try {
        const rawParsed = format === 'pdb' ? parsePdbSequences(text) : parseMmCifSequences(text);
        const parsed = rawParsed.filter(chain => sequenceQuality(chain.sequence) > chain.sequence.length);
        if (parsed.length) {
            emit('diagnostics', { phase: 'source-sequence-parse', format, sourceDetectedFormat: sourceLooksLikeCif(text) ? 'mmcif' : 'pdb', chainCount: parsed.length,
                chains: parsed.map(chain => ({ id: chain.id, residueCount: chain.residueCount, sample: chain.sequence.slice(0, 30), knownResidues: [...chain.sequence].filter(letter => letter !== 'X').length })) });
            return parsed;
        }
        emit('diagnostics', {
            phase: 'source-sequence-parse-empty', format,
            parsedChainCount: rawParsed.length,
            parsedChains: rawParsed.map(chain => ({ id: chain.id, residueCount: chain.residueCount, sample: chain.sequence.slice(0, 30), knownResidues: [...chain.sequence].filter(letter => letter !== 'X').length }))
        });
        emit('console-warning', { message: `Could not recover a known amino-acid sequence from ${format.toUpperCase()} source text; all-X/unknown-only chains are omitted instead of displayed as false sequences.` });
        return [];
    } catch (error) {
        emit('console-warning', { message: `Source sequence parser failed for ${format.toUpperCase()}: ${String(error)}` });
        return [];
    }
}

function getComponentLabel(key: string, fallback = ''): string {
    const normalizedKey = key.replace(/[^a-z]/gi, '').toLowerCase();
    const known: Record<string, string> = {
        polymer: 'Polymer', protein: 'Protein', nucleic: 'Nucleic acids', ligand: 'Ligands',
        water: 'Water', ion: 'Ions', branched: 'Carbohydrates', lipid: 'Lipids',
        coarse: 'Coarse-grained structure', nonstandard: 'Non-standard residues',
        nonstandardpolymer: 'Non-standard residues'
    };
    if (known[normalizedKey]) return known[normalizedKey];
    const normalizedFallback = fallback.replace(/[^a-z]/gi, '').toLowerCase();
    if (known[normalizedFallback]) return known[normalizedFallback];
    return fallback || key || 'Component';
}

function validComponentRefs(value: any): any[] {
    const candidates = Array.isArray(value) ? value : value ? [value] : [];
    return candidates.filter((component: any) =>
        Boolean(component?.cell?.transform?.ref && component?.cell?.obj?.data)
    );
}

function getComponentSummaries(): PublicComponent[] {
    const items: PublicComponent[] = [];
    for (const [id, group] of currentComponents.entries()) {
        const refs = group.refs.filter(ref => ref?.cell?.obj?.data);
        if (!refs.length) continue;
        const atomCount = refs.reduce((sum, ref) => sum + Number(ref.cell.obj.data.elementCount ?? 0), 0);
        if (atomCount <= 0) continue;
        items.push({
            id,
            label: group.label,
            atomCount,
            hidden: refs.every(ref => Boolean(ref.cell?.state?.isHidden)),
            category: group.key
        });
    }
    return items.sort((a, b) => a.label.localeCompare(b.label));
}

type RenderSetting = 'occlusion' | 'shadow' | 'outline';
type CameraMode = 'perspective' | 'orthographic';

// These values match Mol* 5.13.1's public SsaoParams, ShadowParams and
// OutlineParams defaults. Preserve the current params when toggling an effect
// off and back on, using these defaults only the first time it is enabled.
const RENDER_SETTING_DEFAULTS: Record<RenderSetting, Record<string, unknown>> = {
    occlusion: {
        samples: 32,
        multiScale: { name: 'off', params: {} },
        radius: 5,
        bias: 0.8,
        blurKernelSize: 15,
        blurDepthBias: 0.5,
        resolutionScale: 1,
        color: Color(0x000000),
        transparentThreshold: 0.4
    },
    shadow: { steps: 1, maxDistance: 3, tolerance: 1.0 },
    outline: { scale: 1, threshold: 0.33, color: Color(0x000000), includeTransparent: true }
};

function currentViewerSettings(): Record<string, unknown> {
    const props = plugin?.canvas3d?.props;
    if (!props) return {};
    return {
        cameraMode: props.camera.mode,
        occlusion: props.postprocessing.occlusion.name === 'on',
        shadow: props.postprocessing.shadow.name === 'on',
        outline: props.postprocessing.outline.name === 'on',
        illumination: Boolean(props.illumination.enabled)
    };
}

function emitViewerSettings(type = 'settings-state'): void {
    emit(type, { settings: currentViewerSettings() });
}

function setCameraMode(mode: CameraMode): void {
    if (!plugin?.canvas3d) throw new Error('The molecular viewer is not initialized.');
    if (mode !== 'perspective' && mode !== 'orthographic') {
        throw new Error(`Unsupported camera mode: ${String(mode)}`);
    }
    plugin.canvas3d.setProps({ camera: { mode } });
    emitViewerSettings('settings-updated');
}

function setRenderSetting(setting: RenderSetting, enabled: boolean): void {
    if (!plugin?.canvas3d) throw new Error('The molecular viewer is not initialized.');
    if (!(setting in RENDER_SETTING_DEFAULTS)) throw new Error(`Unknown rendering setting: ${String(setting)}`);

    const postprocessing = plugin.canvas3d.props.postprocessing as any;
    const current = postprocessing[setting];
    const next = enabled
        ? {
            name: 'on',
            params: current?.name === 'on' && current.params && Object.keys(current.params).length
                ? current.params
                : RENDER_SETTING_DEFAULTS[setting]
        }
        : { name: 'off', params: {} };
    plugin.canvas3d.setProps({ postprocessing: { [setting]: next } as any });
    emitViewerSettings('settings-updated');
}

function setIllumination(enabled: boolean): void {
    if (!plugin?.canvas3d) throw new Error('The molecular viewer is not initialized.');
    const current = plugin.canvas3d.props.illumination;
    plugin.canvas3d.setProps({ illumination: { ...current, enabled } });

    if (enabled) {
        const extensions = (plugin.canvas3d as any).webgl?.extensions;
        if (extensions && !(extensions.textureFloat && extensions.colorBufferFloat && extensions.depthTexture && extensions.drawBuffers)) {
            emit('console-warning', {
                message: 'Global illumination was enabled, but this WebGL context is missing one or more required extensions. Mol* will fall back to its regular renderer.'
            });
        }
    }
    emitViewerSettings('settings-updated');
}

function refreshComponents(presetResult?: any, sendEvent = true): void {
    const next = new Map<string, ComponentGroup>();
    const addGroup = (rawKey: string, rawRefs: any[]): void => {
        const refs = validComponentRefs(rawRefs);
        if (!refs.length) return;
        // Remove duplicates within a group while preserving hierarchy order.
        const unique = [...new Map(refs.map(ref => [String(ref.cell.transform.ref), ref])).values()];
        if (!unique.length) return;
        const key = String(rawKey || 'component').replace(/\s+/g, '-').toLowerCase();
        const id = `${key}:${unique.map(ref => String(ref.cell.transform.ref)).join(',')}`;
        const fallback = normalizedText(unique[0]?.cell?.obj?.label, 'Component');
        next.set(id, { id, key, label: getComponentLabel(key, fallback), refs: unique });
    };

    // Mol* representation presets return `components` as category -> group,
    // and each group is an array of StructureComponentRef values. Treat the
    // entire group as one UI component so Hide/Delete/Select applies to all of it.
    const resultComponents = presetResult?.components;
    if (resultComponents && typeof resultComponents === 'object') {
        for (const [category, value] of Object.entries(resultComponents)) {
            addGroup(category, validComponentRefs(value));
        }
    }

    // Fallback for presets that do not return a components dictionary. Use
    // Mol*'s public hierarchy refs and group them by a readable component label.
    if (next.size === 0) {
        const hierarchyRefs: any[] = [];
        const directComponents = currentStructureRef?.components;
        if (Array.isArray(directComponents)) hierarchyRefs.push(...directComponents);
        const selectedStructures = plugin?.managers.structure.hierarchy.selection.structures ?? [];
        for (const structureRef of selectedStructures) {
            if (Array.isArray(structureRef?.components)) hierarchyRefs.push(...structureRef.components);
        }
        const groups = new Map<string, any[]>();
        for (const component of validComponentRefs(hierarchyRefs)) {
            const objectLabel = normalizedText(component?.cell?.obj?.label, 'Component');
            const key = objectLabel.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'component';
            const list = groups.get(key) ?? [];
            list.push(component);
            groups.set(key, list);
        }
        for (const [key, refs] of groups) addGroup(key, refs);
    }

    currentComponents = next;
    emit('diagnostics', {
        phase: 'component-catalog', componentCount: currentComponents.size,
        components: getComponentSummaries().map(component => ({ id: component.id, label: component.label, category: component.category, atomCount: component.atomCount, hidden: component.hidden }))
    });
    if (sendEvent) emit('components-updated', { components: getComponentSummaries() });
}

function buildPublicSummary(structure: any, text: string, format: 'pdb' | 'mmcif'): Record<string, unknown> {
    const entitySequences = collectPolymerSequences(structure);
    const sourceSequences = parseSourceSequences(text, format);
    const byId = new Map<string, ChainSummary>();
    // An all-X sequence is not useful to a scientist and was the exact failure
    // visible in the supplied log. Prefer an explicit empty-state message over
    // falsely presenting unknown polymer metadata as an amino-acid sequence.
    const candidates = [...entitySequences, ...sourceSequences].filter(
        candidate => sequenceQuality(candidate.sequence) > candidate.sequence.length
    );
    for (const candidate of candidates) {
        const existing = byId.get(candidate.id);
        if (!existing || sequenceQuality(candidate.sequence) > sequenceQuality(existing.sequence)) byId.set(candidate.id, candidate);
    }
    const chainSummaries = [...byId.values()].sort((a, b) => a.id.localeCompare(b.id));
    emit('diagnostics', {
        phase: 'sequence-summary-complete',
        sequenceSource: sourceSequences.length ? `${format}-source-text`
            : (entitySequences.some(chain => sequenceQuality(chain.sequence) > chain.sequence.length)
                ? 'model.sequence.byEntityKey fallback' : 'none — no recognised amino-acid codes'),
        chainCount: chainSummaries.length,
        chains: chainSummaries.map(chain => ({ id: chain.id, residueCount: chain.residueCount, sample: chain.sequence.slice(0, 30), known: sequenceQuality(chain.sequence) - chain.sequence.length }))
    });
    const proteinResidueCount = chainSummaries.reduce((sum, chain) => sum + chain.residueCount, 0);
    return {
        name: currentName,
        chains: chainSummaries,
        components: getComponentSummaries(),
        proteinResidueCount
    };
}

async function selectComponent(componentId: string): Promise<void> {
    const component = currentComponents.get(componentId);
    if (!plugin || !component) throw new Error('That component is no longer available. Reload the structure and try again.');
    await Promise.resolve(plugin.managers.structure.component.selectThis(component.refs));
    plugin.managers.camera.focusSpheres(component.refs, (entry: any) => entry.cell?.obj?.data?.boundary?.sphere);
    emit('component-selected', { id: componentId, label: component.label });
}

async function toggleComponentVisibility(componentId: string): Promise<void> {
    const component = currentComponents.get(componentId);
    if (!plugin || !component) throw new Error('That component is no longer available.');
    await Promise.resolve(plugin.managers.structure.component.toggleVisibility(component.refs));
    await new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
    emit('components-updated', { components: getComponentSummaries() });
}

async function removeComponent(componentId: string): Promise<void> {
    const component = currentComponents.get(componentId);
    if (!plugin || !component) throw new Error('That component is no longer available.');
    const label = component.label;
    await Promise.resolve(plugin.managers.structure.hierarchy.remove(component.refs, true));
    currentComponents.delete(componentId);
    emit('components-updated', { components: getComponentSummaries() });
    emit('component-removed', { id: componentId, label });
}

async function initialize(): Promise<void> {
    const startedAt = performance.now();
    try {
        if (!canvas || !parent) throw new Error('Mol* canvas container is missing from index.html.');
        emit('diagnostics', {
            phase: 'initialize-start',
            userAgent: navigator.userAgent,
            devicePixelRatio: window.devicePixelRatio,
            viewport: { width: parent.clientWidth, height: parent.clientHeight },
            canvas: { width: canvas.width, height: canvas.height, clientWidth: canvas.clientWidth, clientHeight: canvas.clientHeight },
            url: window.location.href
        });
        plugin = new PluginContext(DefaultPluginSpec());
        await plugin.init();
        // Mol*'s own log stream is valuable for WebGL, representation and state
        // errors that do not become ordinary JavaScript exceptions.
        plugin.events.log.subscribe((entry: any) => {
            const severity = String(entry?.type ?? entry?.level ?? 'info');
            const message = String(entry?.message ?? entry?.data ?? entry);
            emit('molstar-log', { severity, message });
        });
        const supported = await plugin.initViewerAsync(canvas, parent);
        if (!supported) throw new Error('WebGL initialization failed. Check WebKitGTK, GPU drivers, and hardware acceleration.');

        // Start opaque and visible. Transparent WebGL compositing is driver- and
        // WebKit-dependent, and can otherwise make the first successful render
        // appear blank. The native toggle can enable it after initialization.
        plugin.canvas3d?.setProps({
            transparentBackground: false,
            checkeredTransparentBackground: false,
            renderer: { backgroundColor: Color(0xFCFBF9) }
        });
        document.documentElement.style.backgroundColor = '#fcfbf9';
        document.body.style.backgroundColor = '#fcfbf9';
        parent.style.backgroundColor = '#fcfbf9';

        window.proteinViewer = {
            loadStructureText,
            setBackground,
            setRepresentation,
            resetCamera,
            orientAxes,
            resetAxes,
            setCameraMode,
            setRenderSetting,
            setIllumination,
            selectComponent,
            toggleComponentVisibility,
            removeComponent
        };
        emit('diagnostics', {
            phase: 'initialize-complete',
            elapsedMs: Math.round(performance.now() - startedAt),
            webglInitialized: Boolean(plugin.canvas3d),
            viewport: { width: parent.clientWidth, height: parent.clientHeight },
            canvas: { width: canvas.width, height: canvas.height, clientWidth: canvas.clientWidth, clientHeight: canvas.clientHeight }
        });
        emitViewerSettings();
        emit('ready', { molstar: '5.13.1', frontendBuild: FRONTEND_BUILD });
    } catch (error) {
        const detail = errorText(error);
        console.error('Mol* initialization failed', error);
        showFatal(`Mol* could not initialize.\n${detail.message}\n${detail.stack}\n\nCheck WebGL support and rebuild the bundled frontend.`);
    }
}

async function loadStructureText(text: string, name: string): Promise<void> {
    if (!plugin) throw new Error('The Mol* viewer is not initialized.');
    if (typeof text !== 'string' || !text.trim()) throw new Error('The structure data is empty.');
    const startedAt = performance.now();
    emit('diagnostics', { phase: 'structure-load-start', name, characterCount: text.length });
    try {
        emit('loading', { name });
        await plugin.clear();
        currentComponents.clear();
        currentName = name;
        currentSourceText = text;
        const format = detectStructureFormat(name, text);
        emit('diagnostics', { phase: 'parse-start', name, format });
        const data = await plugin.builders.data.rawData({ data: text, label: name });
        const trajectory = await plugin.builders.structure.parseTrajectory(data, format as any);
        emit('diagnostics', { phase: 'parse-complete', name, frameCount: trajectory?.frameCount ?? null });
        const presetResult = await plugin.builders.structure.hierarchy.applyPreset(trajectory, 'default');
        currentStructureRef = plugin.managers.structure.hierarchy.current.structures[0];
        currentStructure = currentStructureRef?.cell?.obj?.data;
        if (!currentStructure) {
            throw new Error(`Mol* parsed ${name} but did not create a current structure (preset result: ${String(presetResult)}).`);
        }
        currentFormat = format;
        refreshComponents(presetResult, false);

        // Make the canvas re-layout and fit the molecular object after the async
        // state update; this is useful in a GTK WebView whose first size can be 0.
        await new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
        plugin.canvas3d?.requestResize();
        plugin.canvas3d?.requestCameraReset();
        fatal.style.display = 'none';

        const summary = buildPublicSummary(currentStructure, currentSourceText, currentFormat);
        emit('render-diagnostics', {
            name,
            elementCount: currentStructure.elementCount ?? null,
            unitCount: currentStructure.units?.length ?? null,
            polymerResidueCount: currentStructure.polymerResidueCount ?? null,
            canvas: { width: canvas.width, height: canvas.height, clientWidth: canvas.clientWidth, clientHeight: canvas.clientHeight },
            viewport: { width: parent.clientWidth, height: parent.clientHeight },
            transparentBackground: Boolean((plugin.canvas3d as any)?.props?.transparentBackground),
            elapsedMs: Math.round(performance.now() - startedAt),
            sequenceChains: (summary.chains as ChainSummary[]).map(chain => ({ id: chain.id, residueCount: chain.residueCount, sample: chain.sequence.slice(0, 20) })),
            components: getComponentSummaries().map(component => ({ label: component.label, atomCount: component.atomCount }))
        });
        if (summary.proteinResidueCount === 0) {
            emit('console-warning', { message: 'Mol* rendered a structure but no protein residues were detected in the sequence scanner.' });
        }
        emit('structure-loaded', summary);
        emit('components-updated', { components: getComponentSummaries() });
    } catch (error) {
        const detail = errorText(error);
        console.error(`Could not load ${name}`, error);
        emit('error', { message: `Could not load ${name}: ${detail.message}`, stack: detail.stack });
        throw error;
    }
}

function setBackground(mode: 'transparent' | 'light' | 'dark'): void {
    if (!plugin?.canvas3d) {
        emit('console-warning', { message: `setBackground(${mode}) called before Canvas3D exists.` });
        return;
    }
    try {
        if (mode === 'transparent') {
            document.documentElement.style.backgroundColor = 'transparent';
            document.body.style.backgroundColor = 'transparent';
            parent.style.backgroundColor = 'transparent';
            plugin.canvas3d.setProps({ transparentBackground: true, checkeredTransparentBackground: false });
        } else {
            const background = mode === 'dark' ? '#1e1e1e' : '#f6f5f4';
            document.documentElement.style.backgroundColor = background;
            document.body.style.backgroundColor = background;
            parent.style.backgroundColor = background;
            plugin.canvas3d.setProps({
                transparentBackground: false,
                checkeredTransparentBackground: false,
                renderer: { backgroundColor: Color(mode === 'dark' ? 0x1e1e1e : 0xf6f5f4) }
            });
        }
        emit('diagnostics', {
            phase: 'background-updated', mode,
            canvas: { width: canvas.width, height: canvas.height, clientWidth: canvas.clientWidth, clientHeight: canvas.clientHeight }
        });
        emit('background-changed', { mode });
    } catch (error) {
        const detail = errorText(error);
        console.error('Could not change viewport background', error);
        emit('error', { message: `Could not change the viewport background: ${detail.message}`, stack: detail.stack });
    }
}

async function setRepresentation(name: string): Promise<void> {
    if (!plugin || !currentStructureRef) return;
    const preset = PRESETS[name];
    if (!preset) {
        emit('error', { message: `Unknown representation preset: ${name}` });
        return;
    }
    try {
        const result = await plugin.builders.structure.representation.applyPreset(currentStructureRef.cell.transform.ref, preset as any);
        refreshComponents(result, false);
        emit('representation-changed', { name });
        emit('components-updated', { components: getComponentSummaries() });
    } catch (error) {
        console.error('Representation change failed', error);
        emit('error', { message: `Could not apply the ${name} representation: ${String(error)}` });
    }
}

function resetCamera(): void {
    try {
        plugin?.canvas3d?.requestCameraReset();
    } catch (error) {
        emit('error', { message: `Could not reset zoom: ${String(error)}` });
    }
}

async function orientAxes(): Promise<void> {
    if (!plugin) throw new Error('The molecular viewer is not initialized.');
    try {
        await PluginCommands.Camera.OrientAxes(plugin, {});
    } catch (error) {
        emit('error', { message: `Could not orient the molecular axes: ${String(error)}` });
        throw error;
    }
}

async function resetAxes(): Promise<void> {
    if (!plugin) throw new Error('The molecular viewer is not initialized.');
    try {
        await PluginCommands.Camera.ResetAxes(plugin, {});
    } catch (error) {
        emit('error', { message: `Could not reset the molecular axes: ${String(error)}` });
        throw error;
    }
}

void initialize();

window.addEventListener('beforeunload', () => {
    try { plugin?.dispose(); } catch (error) { console.warn('Mol* cleanup failed', error); }
});
