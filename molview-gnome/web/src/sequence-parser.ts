/** Source-text protein sequence extraction for PDB and mmCIF structures. */

export type ChainSummary = { id: string; sequence: string; residueCount: number };

export function sourceLooksLikeCif(text: string): boolean {
    const header = text.slice(0, Math.min(text.length, 250_000));
    return /(^|\n)\s*data_[^\s]+/i.test(header)
        && /_atom_site\.|_entity_poly\./i.test(header);
}

export function detectStructureFormat(name: string, text: string): 'pdb' | 'mmcif' {
    // Inspect content before trusting the filename. Some structure files are
    // renamed after download, and parsing mmCIF as PDB can yield bad metadata.
    if (sourceLooksLikeCif(text)) return 'mmcif';
    const lower = name.toLowerCase();
    if (lower.endsWith('.cif') || lower.endsWith('.mmcif')) return 'mmcif';
    return 'pdb';
}

export const AA_ONE: Record<string, string> = {
    ALA: 'A', ARG: 'R', ASN: 'N', ASP: 'D', CYS: 'C', GLN: 'Q', GLU: 'E',
    GLY: 'G', HIS: 'H', ILE: 'I', LEU: 'L', LYS: 'K', MET: 'M', PHE: 'F',
    PRO: 'P', SER: 'S', THR: 'T', TRP: 'W', TYR: 'Y', VAL: 'V', MSE: 'M',
    SEC: 'U', PYL: 'O', UNK: 'X',
    // Common modified/alternative residue names in PDB files.
    HID: 'H', HIE: 'H', HIP: 'H', HSD: 'H', HSE: 'H', HSP: 'H',
    ASH: 'D', GLH: 'E', LYN: 'K', CYM: 'C', CYX: 'C', CYS2: 'C',
    HYP: 'P', MHO: 'M', FME: 'M', NLE: 'L', SEP: 'S', TPO: 'T',
    PTR: 'Y', CSO: 'C', CSD: 'C', CME: 'C', OCS: 'C', PCA: 'E'
};
export function sequenceQuality(sequence: string): number {
    let known = 0;
    for (const residue of sequence) if (residue !== 'X' && /[ACDEFGHIKLMNPQRSTVWYUO]/.test(residue)) known++;
    return known * 1_000_000 + sequence.length;
}

function normalizeChainId(value: string): string {
    const trimmed = value.trim();
    return trimmed || '(blank)';
}

export function sequenceFromResidueNames(names: string[]): string {
    return names.map(name => {
        const normalized = name.trim().toUpperCase();
        if (normalized.length === 1 && /[A-Z]/.test(normalized)) return normalized;
        return AA_ONE[normalized] ?? 'X';
    }).join('');
}

export function parsePdbSequences(text: string): ChainSummary[] {
    const seqres = new Map<string, string[]>();
    const observed = new Map<string, string[]>();
    const seenObserved = new Map<string, Set<string>>();

    for (const line of text.split(/\r?\n/)) {
        const record = line.slice(0, 6).trim().toUpperCase();
        if (record === 'SEQRES') {
            const chain = normalizeChainId(line.slice(11, 12));
            const residueNames = line.slice(19, 70).trim().split(/\s+/).filter(Boolean);
            const target = seqres.get(chain) ?? [];
            target.push(...residueNames);
            seqres.set(chain, target);
        } else if (record === 'ATOM' || record === 'HETATM') {
            // Standard ATOM records are polymer residues, including uncommon
            // component names (which become X). HETATM residues are included
            // only if their component code is a known amino acid/modification.
            const compId = line.slice(17, 20).trim().toUpperCase();
            const recordIsAtom = record === 'ATOM';
            if (!AA_ONE[compId] && !recordIsAtom) continue;
            if (compId === 'UNK' && !recordIsAtom) continue;
            const chain = normalizeChainId(line.slice(21, 22));
            const seq = line.slice(22, 26).trim();
            const ins = line.slice(26, 27).trim();
            if (!seq) continue;
            const key = `${seq}:${ins}`;
            const seen = seenObserved.get(chain) ?? new Set<string>();
            if (seen.has(key)) continue;
            seen.add(key);
            seenObserved.set(chain, seen);
            const target = observed.get(chain) ?? [];
            target.push(compId);
            observed.set(chain, target);
        }
    }

    const chainIds = new Set([...seqres.keys(), ...observed.keys()]);
    const summaries: ChainSummary[] = [];
    for (const id of chainIds) {
        const seqresNames = seqres.get(id);
        const observedNames = observed.get(id);
        const seqresSequence = seqresNames ? sequenceFromResidueNames(seqresNames) : '';
        const observedSequence = observedNames ? sequenceFromResidueNames(observedNames) : '';
        const sequence = sequenceQuality(seqresSequence) >= sequenceQuality(observedSequence)
            ? seqresSequence : observedSequence;
        if (!sequence) continue;
        summaries.push({ id, sequence, residueCount: sequence.length });
    }
    return summaries.sort((a, b) => a.id.localeCompare(b.id));
}

function tokenizeCif(text: string): string[] {
    const tokens: string[] = [];
    let i = 0;
    while (i < text.length) {
        const atLineStart = i === 0 || text[i - 1] === '\n';
        const ch = text[i];
        if (atLineStart && ch === ';') {
            i++;
            if (text[i] === '\r') i++;
            if (text[i] === '\n') i++;
            const begin = i;
            let end = text.length;
            while (i < text.length) {
                if ((i === 0 || text[i - 1] === '\n') && text[i] === ';') {
                    end = i;
                    while (i < text.length && text[i] !== '\n') i++;
                    if (text[i] === '\n') i++;
                    break;
                }
                i++;
            }
            tokens.push(text.slice(begin, end).replace(/\r?\n$/, '').trim());
            continue;
        }
        if (/\s/.test(ch)) { i++; continue; }
        if (ch === '#') {
            while (i < text.length && text[i] !== '\n') i++;
            continue;
        }
        if (ch === "'" || ch === '"') {
            const quote = ch;
            i++;
            const begin = i;
            while (i < text.length) {
                if (text[i] === quote && (i + 1 === text.length || /\s|#/.test(text[i + 1]))) break;
                i++;
            }
            tokens.push(text.slice(begin, i));
            if (text[i] === quote) i++;
            continue;
        }
        const begin = i;
        while (i < text.length && !/\s/.test(text[i]) && text[i] !== '#') i++;
        tokens.push(text.slice(begin, i));
    }
    return tokens;
}

type CifTable = { headers: string[]; rows: Array<Record<string, string>> };

function parseCifTables(text: string): CifTable[] {
    const tokens = tokenizeCif(text);
    const tables: CifTable[] = [];
    let i = 0;
    while (i < tokens.length) {
        if (tokens[i].toLowerCase() !== 'loop_') { i++; continue; }
        i++;
        const headers: string[] = [];
        while (i < tokens.length && tokens[i].startsWith('_')) headers.push(tokens[i++].toLowerCase());
        if (!headers.length) continue;
        const values: string[] = [];
        while (i < tokens.length) {
            const token = tokens[i];
            const boundary = values.length % headers.length === 0 && (
                token.toLowerCase() === 'loop_' || token.toLowerCase() === 'stop_' ||
                token.toLowerCase().startsWith('data_') || token.toLowerCase().startsWith('save_') || token.startsWith('_')
            );
            if (boundary) break;
            values.push(token);
            i++;
        }
        const rows: Array<Record<string, string>> = [];
        for (let start = 0; start + headers.length <= values.length; start += headers.length) {
            const row: Record<string, string> = {};
            for (let col = 0; col < headers.length; col++) row[headers[col]] = values[start + col];
            rows.push(row);
        }
        if (rows.length) tables.push({ headers, rows });
        if (i < tokens.length && tokens[i].toLowerCase() === 'stop_') i++;
    }
    return tables;
}

export function parseMmCifSequences(text: string): ChainSummary[] {
    const tables = parseCifTables(text);
    const entityTable = tables.find(table => table.headers.includes('_entity_poly.entity_id'));
    const asymTable = tables.find(table => table.headers.includes('_struct_asym.id') && table.headers.includes('_struct_asym.entity_id'));
    const atomTable = tables.find(table => table.headers.includes('_atom_site.label_asym_id') && table.headers.includes('_atom_site.auth_asym_id'));
    if (!atomTable && (!entityTable || !asymTable)) return [];

    const entitySequences = new Map<string, string>();
    for (const row of entityTable?.rows ?? []) {
        const entityId = row['_entity_poly.entity_id'];
        const entityType = (row['_entity_poly.type'] || '').toLowerCase();
        if (entityType && !entityType.includes('polypeptide')) continue;
        const raw = row['_entity_poly.pdbx_seq_one_letter_code_can'] || row['_entity_poly.pdbx_seq_one_letter_code'] || '';
        const sequence = raw.replace(/\([^)]*\)/g, '').replace(/[^A-Za-z]/g, '').toUpperCase();
        if (entityId && sequence) entitySequences.set(entityId, sequence);
    }
    const authByLabel = new Map<string, string>();
    const observed = new Map<string, string[]>();
    const observedKeys = new Map<string, Set<string>>();
    if (atomTable) {
        for (const row of atomTable.rows) {
            const label = row['_atom_site.label_asym_id'];
            const authRaw = row['_atom_site.auth_asym_id'];
            const auth = authRaw && authRaw !== '.' && authRaw !== '?' ? authRaw : '';
            if (label && label !== '.' && label !== '?' && auth && !authByLabel.has(label)) authByLabel.set(label, auth);
        }
        // A malformed or incomplete entity_poly sequence should not force the
        // entire chain to X. Recover observed residues from atom_site when a
        // recognised amino-acid component is present.
        const headers = new Set(atomTable.headers);
        if (headers.has('_atom_site.label_comp_id') || headers.has('_atom_site.auth_comp_id')) {
            for (const row of atomTable.rows) {
                const group = (row['_atom_site.group_pdb'] || 'ATOM').toUpperCase();
                const labelComp = (row['_atom_site.label_comp_id'] || '').toUpperCase();
                const authComp = (row['_atom_site.auth_comp_id'] || '').toUpperCase();
                const compId = [labelComp, authComp].find(code => Boolean(AA_ONE[code] && AA_ONE[code] !== 'X'))
                    || labelComp || authComp;
                const letter = AA_ONE[compId];
                if (!letter || letter === 'X') continue;
                if (group !== 'ATOM' && group !== 'HETATM') continue;
                const authChain = row['_atom_site.auth_asym_id'];
                const labelChain = row['_atom_site.label_asym_id'];
                const rawChain = authChain && authChain !== '.' && authChain !== '?' ? authChain : labelChain;
                const chain = normalizeChainId(rawChain && rawChain !== '.' && rawChain !== '?' ? rawChain : '');
                const authSeq = row['_atom_site.auth_seq_id'];
                const labelSeq = row['_atom_site.label_seq_id'];
                const seqNo = authSeq && authSeq !== '.' && authSeq !== '?' ? authSeq
                    : (labelSeq && labelSeq !== '.' && labelSeq !== '?' ? labelSeq : '');
                const rawIns = row['_atom_site.pdbx_pdb_ins_code'] || '';
                const ins = rawIns === '.' || rawIns === '?' ? '' : rawIns;
                if (!seqNo) continue;
                const key = `${seqNo}:${ins}`;
                const seen = observedKeys.get(chain) ?? new Set<string>();
                if (seen.has(key)) continue;
                seen.add(key);
                observedKeys.set(chain, seen);
                const residues = observed.get(chain) ?? [];
                residues.push(compId);
                observed.set(chain, residues);
            }
        }
    }
    const byChain = new Map<string, ChainSummary>();
    for (const row of asymTable?.rows ?? []) {
        const labelChain = row['_struct_asym.id'];
        const entityId = row['_struct_asym.entity_id'];
        const entitySequence = entitySequences.get(entityId) || '';
        const id = normalizeChainId(authByLabel.get(labelChain) || labelChain);
        const observedSequence = sequenceFromResidueNames(observed.get(id) ?? []);
        const sequence = sequenceQuality(entitySequence) > sequenceQuality(observedSequence)
            ? entitySequence : observedSequence;
        if (!sequence) continue;
        const candidate = { id, sequence, residueCount: sequence.length };
        const current = byChain.get(id);
        if (!current || sequenceQuality(sequence) > sequenceQuality(current.sequence)) byChain.set(id, candidate);
    }
    // Some CIF variants lack struct_asym/entity_poly tables. Still expose chains
    // recoverable from atom_site if their observed residues are amino acids.
    for (const [id, names] of observed) {
        if (byChain.has(id) || !names.length) continue;
        const sequence = sequenceFromResidueNames(names);
        if (sequenceQuality(sequence) > sequence.length) byChain.set(id, { id, sequence, residueCount: sequence.length });
    }
    return [...byChain.values()].sort((a, b) => a.id.localeCompare(b.id));
}

