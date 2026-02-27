const http = require('http');

function checkPage(port, path) {
  return new Promise((resolve, reject) => {
    const req = http.get(`http://localhost:${port}${path}`, (r) => {
      let d = '';
      r.on('data', (c) => d += c);
      r.on('end', () => {
        resolve({ status: r.statusCode, body: d });
      });
    });
    req.on('error', (e) => reject(e));
    req.setTimeout(5000, () => { req.destroy(); reject(new Error('timeout')); });
  });
}

async function main() {
  // Check deployed build on port 3002
  try {
    const res = await checkPage(3002, '/');
    console.log('=== PORT 3002 (deployed) ===');
    console.log('Status:', res.status);
    console.log('Has buildManifest:', res.body.includes('buildManifest'));
    console.log('Has _ssgManifest:', res.body.includes('ssgManifest'));
    console.log('Has __next_f:', res.body.includes('__next_f'));
    
    // Check for BUILD_ID references
    const bidMatch = res.body.match(/Kqe6vWtV[^"']*/g);
    console.log('BUILD_ID refs:', bidMatch);
    
    // List all script src
    const scripts = res.body.match(/src="([^"]+)"/g);
    console.log('\nAll src= references:');
    if (scripts) scripts.forEach(s => console.log('  ', s));
    
    // List all href
    const hrefs = res.body.match(/href="([^"]+)"/g);
    console.log('\nAll href= references:');
    if (hrefs) hrefs.forEach(h => console.log('  ', h));

    // Check for inline scripts that reference buildManifest
    const inlineScripts = res.body.match(/<script[^>]*>[^<]*buildManifest[^<]*<\/script>/g);
    console.log('\nInline scripts with buildManifest:', inlineScripts ? inlineScripts.length : 0);
    if (inlineScripts) inlineScripts.forEach(s => console.log('  ', s.substring(0, 200)));
    
  } catch (e) {
    console.log('Port 3002 error:', e.message);
  }

  // Also check a subpage
  try {
    const res2 = await checkPage(3002, '/marketplace');
    console.log('\n=== /marketplace ===');
    console.log('Status:', res2.status);
    console.log('Length:', res2.body.length);
    console.log('Has Application error:', res2.body.includes('Application error'));
  } catch (e) {
    console.log('marketplace error:', e.message);
  }
}

main();
