async function main() {
  const r = await fetch('http://localhost:4000/api/election/status');
  const j = await r.json();
  const e = j.data?.currentElection;
  if (!e) { console.log('NO ELECTION'); return; }
  console.log(`Phase: ${e.phase} | Term: ${e.term} | Candidates: ${e.candidates.length}`);
  for (const c of e.candidates) {
    console.log(`  - ${c.agentName}: ${c.slogan}`);
  }
}
main().catch(console.error);
