const puppeteer = require('puppeteer');
const path = require('path');

(async () => {
  const browser = await puppeteer.launch({
    headless: true,
    executablePath: 'C:\\Users\\gkjuw\\.cache\\puppeteer\\chrome\\win64-145.0.7632.77\\chrome-win64\\chrome.exe',
    timeout: 90000,
    protocolTimeout: 90000,
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-gpu',
      '--no-first-run',
      '--no-zygote',
      '--single-process',
    ],
  });

  const cards = [
    { html: 'business_card.html', output: 'business_card_front.png', label: 'FRONT' },
    { html: 'business_card_back.html', output: 'business_card_back.png', label: 'BACK' },
  ];

  for (const card of cards) {
    const page = await browser.newPage();
    await page.setViewport({ width: 1050, height: 600, deviceScaleFactor: 2 });

    const filePath = path.join(__dirname, card.html);
    await page.goto('file:///' + filePath.replace(/\\/g, '/'), { waitUntil: 'networkidle0', timeout: 30000 });

    // Wait for fonts to load
    await page.evaluate(() => document.fonts.ready);
    await new Promise(r => setTimeout(r, 1500));

    const outputPath = path.join(__dirname, '..', card.output);
    await page.screenshot({
      path: outputPath,
      type: 'png',
      clip: { x: 0, y: 0, width: 1050, height: 600 },
      omitBackground: false,
    });

    console.log(`${card.label}: ${outputPath}`);
    await page.close();
  }

  await browser.close();
  console.log('\nDone! Business cards saved to ai_master/');
})();
