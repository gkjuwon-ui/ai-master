export function extractFirstJsonObject(text: string): string | null {
  const start = text.indexOf('{');
  if (start === -1) return null;
  let depth = 0;
  for (let i = start; i < text.length; i++) {
    const ch = text[i];
    if (ch === '{') depth++;
    else if (ch === '}') {
      depth--;
      if (depth === 0) return text.slice(start, i + 1);
    }
  }
  return null; // incomplete
}

// Best-effort salvage for truncated/malformed judge JSON without calling LLM.
// Heuristics:
// - try to parse direct extraction
// - if parsing fails, attempt to close any unterminated final string and balance braces
// - make minimal edits (close the last open quote and append '}'s) so the object becomes valid JSON
export function salvageMalformedJudgeRaw(raw: string): any | null {
  if (!raw || typeof raw !== 'string') return null;

  // 1) try clean extraction
  const extracted = extractFirstJsonObject(raw);
  if (extracted) {
    try { return JSON.parse(extracted); } catch (_) { /* fall through */ }
  }

  // 2) attempt best-effort repair on the substring starting at first '{'
  const start = raw.indexOf('{');
  if (start === -1) return null;
  let candidate = raw.slice(start);

  // If there are more characters after the JSON that clearly belong to the outer record
  // (e.g. '"domain":' appears), cut candidate before that marker.
  const outerMarker = candidate.indexOf('\n"domain":');
  if (outerMarker !== -1) candidate = candidate.slice(0, outerMarker);

  // Count quotation marks to detect unterminated string
  const quoteCount = (candidate.match(/"/g) || []).length;
  if (quoteCount % 2 === 1) {
    // close the last open string with a quote and add an ellipsis to indicate truncation
    candidate = candidate + '..."';
  }

  // Balance braces by appending closing '}' until depth == 0 or until a small limit
  let depth = 0;
  for (let i = 0; i < candidate.length; i++) {
    const ch = candidate[i];
    if (ch === '{') depth++; else if (ch === '}') depth--;
  }
  const maxAppend = 6;
  let appendCount = 0;
  while (depth > 0 && appendCount < maxAppend) {
    candidate += '}';
    depth--;
    appendCount++;
  }

  // Final attempt to parse
  try {
    return JSON.parse(candidate);
  } catch (_) {
    return null;
  }
}
