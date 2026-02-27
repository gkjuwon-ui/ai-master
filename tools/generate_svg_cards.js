/**
 * generate_svg_cards.js   3-Layer Print-Ready SVG
 *
 * Layer architecture (printed as separate passes):
 *   L1  id="l1-matte-bg"     무광 기저  검은 배경, 그리드, 장식선, 코너 마크
 *   L2  id="l2-matte-text"   무광 텍스트  태그라인, 연락처, just watch., 구분선
 *   L3  id="l3-spot-uv"      유광 Spot UV  브랜드명, 이름, 직함, 로고마크, 오렌지 바
 *
 * Print spec:
 *   FOGRA39 (ISO 12647-2 coated offset)
 *   Physical 90mm x 54mm bleed 3mm => artboard 96mm x 60mm
 *   All text => vector path outlines via opentype.js
 *   CMYK via icc-color(FOGRA39, C, M, Y, K)
 *
 * Usage:  node generate_svg_cards.js
 * Output: ../business_card_front.svg   ../business_card_back.svg
 */

'use strict';

const opentype = require('opentype.js');
const path = require('path');
const fs = require('fs');

const FP = (name, wt) =>
  path.join(__dirname, `node_modules/@fontsource/${name}/files/${name}-latin-${wt}-normal.woff`);

const FONT = {
  inter800: opentype.loadSync(FP('inter', '800')),
  inter700: opentype.loadSync(FP('inter', '700')),
  inter500: opentype.loadSync(FP('inter', '500')),
  inter400: opentype.loadSync(FP('inter', '400')),
  jb400:    opentype.loadSync(FP('jetbrains-mono', '400')),
  jb500:    opentype.loadSync(FP('jetbrains-mono', '500')),
};

const COLOR = {
  orange:  { hex: '#E86520', icc: '0, 0.565, 0.863, 0.09'  },
  orange2: { hex: '#F08535', icc: '0, 0.446, 0.779, 0.059' },
  black:   { hex: '#000000', icc: '0, 0, 0, 1'             },
  white:   { hex: '#FFFFFF', icc: '0, 0, 0, 0'             },
  white70: { hex: '#B2B2B2', icc: '0, 0, 0, 0.302'        },
  white60: { hex: '#999999', icc: '0, 0, 0, 0.4'           },
  white35: { hex: '#595959', icc: '0, 0, 0, 0.651'        },
  white20: { hex: '#333333', icc: '0, 0, 0, 0.8'           },
};

const fill   = c      => `fill="${c.hex}" color="icc-color(FOGRA39, ${c.icc})"`;
const stroke = (c,w=1)=> `stroke="${c.hex}" color="icc-color(FOGRA39, ${c.icc})" stroke-width="${w}" fill="none"`;

function tp(font, text, x, y, sz, opts = {}) {
  const ls = opts.letterSpacing || 0;
  const c  = opts.fill || COLOR.white;
  let d = '', cx = x;
  for (const ch of text) {
    const raw = font.getPath(ch, cx, y, sz).toSVG(3);
    const m = raw.match(/d="([^"]*)"/);
    if (m && m[1]) d += m[1] + ' ';
    cx += font.getAdvanceWidth(ch, sz) + ls;
  }
  const idAttr = opts.id ? ` id="${opts.id}"` : '';
  return d.trim() ? `<path${idAttr} ${fill(c)} d="${d.trim()}"/>` : '';
}

const tw = (font, text, sz, ls = 0) =>
  [...text].reduce((s, ch, i) => s + font.getAdvanceWidth(ch, sz) + (i < text.length-1 ? ls : 0), 0);

const asc = (f, sz) => (f.ascender / f.unitsPerEm) * sz;

function wrapSVG({ defs, l1, l2, l3 }, label) {
  return `<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<!--
  ${label}
  LAYER STRUCTURE:
    l1-matte-bg   -> 무광 기저  (matte laminate pass)
    l2-matte-text -> 무광 텍스트 (matte laminate, same plate)
    l3-spot-uv    -> 유광 Spot UV (UV varnish pass)

  Print spec : FOGRA39 (ISO 12647-2 coated offset)
  Artboard   : 96mm x 60mm  (trim 90mm x 54mm, bleed 3mm/side)
  All text   : vector path outlines
  CMYK       : icc-color(FOGRA39, C, M, Y, K)
-->
<svg version="1.1"
  xmlns="http://www.w3.org/2000/svg"
  xmlns:xlink="http://www.w3.org/1999/xlink"
  xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
  width="96mm" height="60mm"
  viewBox="0 0 1120 700">

  <defs>
    <color-profile name="FOGRA39"
      xlink:href="https://www.color.org/chardata/rgb/sRGB.xalter"
      rendering-intent="perceptual"/>
    <pattern id="gridpat" width="30" height="30" patternUnits="userSpaceOnUse">
      <path d="M 30 0 L 0 0 0 30" fill="none" stroke="white"
            stroke-width="0.5" stroke-opacity="0.02"/>
    </pattern>
    ${defs || ''}
  </defs>

  <!-- L1: 무광 배경 (Matte Background) -->
  <g id="l1-matte-bg"
     inkscape:groupmode="layer"
     inkscape:label="L1 무광 배경 (Matte Background)">
    <rect x="0" y="0" width="1120" height="700" ${fill(COLOR.black)}/>
    <g id="l1-card" transform="translate(35, 50)">
      ${l1 || ''}
    </g>
  </g>

  <!-- L2: 무광 텍스트 (Matte Text  same laminate pass as L1) -->
  <g id="l2-matte-text"
     inkscape:groupmode="layer"
     inkscape:label="L2 무광 텍스트 (Matte Text)">
    <g transform="translate(35, 50)">
      ${l2 || ''}
    </g>
  </g>

  <!-- L3: 유광 Spot UV  NOTE TO PRINTER: UV varnish mask -->
  <!-- All shapes in this group receive gloss UV coating -->
  <g id="l3-spot-uv"
     inkscape:groupmode="layer"
     inkscape:label="L3 유광 Spot UV (Gloss Varnish Pass)">
    <g transform="translate(35, 50)">
      ${l3 || ''}
    </g>
  </g>

  <!-- Crop marks (outside laminate area) -->
  <g id="cropmarks" stroke="#000000" stroke-width="0.5" fill="none" opacity="0.4">
    <line x1="35"   y1="10"  x2="35"   y2="28"/> <line x1="10"  y1="50"  x2="28"  y2="50"/>
    <line x1="1085" y1="10"  x2="1085" y2="28"/> <line x1="1092" y1="50" x2="1110" y2="50"/>
    <line x1="35"   y1="672" x2="35"   y2="690"/><line x1="10"  y1="650" x2="28"  y2="650"/>
    <line x1="1085" y1="672" x2="1085" y2="690"/><line x1="1092" y1="650" x2="1110" y2="650"/>
  </g>

</svg>`;
}

// ==========================================================================
// FRONT CARD
// ==========================================================================
function buildFront() {
  const W = 1050, H = 600;
  const padL = 56, padR = 56, padT = 52, padB = 52;

  const logoRowTopY    = padT;
  const logoRowH       = 44;
  const logoRowCenterY = logoRowTopY + logoRowH / 2;

  const oSz    = 32;
  const oBaseY = logoRowCenterY + (asc(FONT.inter800,oSz) - (Math.abs(FONT.inter800.descender/FONT.inter800.unitsPerEm)*oSz)) / 2;

  const logoMarkX  = padL;
  const logoMarkY  = logoRowTopY;
  const logoTextX  = padL + 44 + 14;

  const oText  = 'ogenti';
  const oWidth = tw(FONT.inter800, oText, oSz);
  const dotX   = logoTextX + oWidth + 2;
  const dotY   = oBaseY - oSz * 0.18;
  const dotR   = 5;

  const nameBlockY = logoRowTopY + logoRowH + 20 + 6;

  const nSz    = 28;
  const nBaseY = nameBlockY + asc(FONT.inter700, nSz);

  const titleText = 'FOUNDER & CEO';
  const tSz    = 14;
  const tBaseY = nameBlockY + nSz + 6 + asc(FONT.inter500, tSz);

  const titleBoxH = nSz + 6 + tSz;
  const sepY   = nameBlockY + titleBoxH + 10;
  const sepX1  = padL, sepX2 = padL + 40;

  const tagSz    = 11.5;
  const tagBaseY = sepY + 4 + asc(FONT.jb400, tagSz);

  const bottomY      = H - padB;
  const iconSz       = 14, contactGap = 7;
  const contactLineH = Math.max(iconSz, tagSz * 1.2);
  const emailLineBaseY = bottomY - (contactLineH + contactGap + contactLineH) + asc(FONT.jb400, 11.5);
  const webLineBaseY   = emailLineBaseY + contactLineH + contactGap;
  const emailLineCenterY = emailLineBaseY - asc(FONT.jb400, 11.5) + contactLineH / 2;
  const webLineCenterY   = webLineBaseY   - asc(FONT.jb400, 11.5) + contactLineH / 2;
  const contactTextX = padL + iconSz + 10;

  const badgeSz1 = 13, badgeSz2 = 9.5, badgeGap = 6;
  const badgeTotalH = badgeSz1 + badgeGap + badgeSz2;
  const jw_base = bottomY - badgeTotalH + asc(FONT.jb500, badgeSz1);
  const yw_base = jw_base + badgeSz1 + badgeGap;
  const jw_text = 'just watch.';
  const yw_text = 'Your agents work for you';
  const jw_w = tw(FONT.jb500, jw_text, badgeSz1);
  const yw_w = tw(FONT.jb400, yw_text, badgeSz2);
  const badgeRightX = W - padR;
  const jw_x = badgeRightX - jw_w;
  const yw_x = badgeRightX - yw_w;

  const accentX   = W - 280;
  const accentRad = 12 * Math.PI / 180;
  const ax1 = accentX, ay1 = 0;
  const ax2 = accentX + H * Math.tan(accentRad), ay2 = H;

  const defs = `
    <linearGradient id="edgeTopGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%"   stop-color="#E86520" stop-opacity="1"/>
      <stop offset="30%"  stop-color="#F08535" stop-opacity="1"/>
      <stop offset="70%"  stop-color="#E86520" stop-opacity="0"/>
      <stop offset="100%" stop-color="#E86520" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="edgeBotGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%"   stop-color="#E86520" stop-opacity="0"/>
      <stop offset="100%" stop-color="#E86520" stop-opacity="0.3"/>
    </linearGradient>
    <linearGradient id="accentLineGrad" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%"   stop-color="#E86520" stop-opacity="0"/>
      <stop offset="30%"  stop-color="#E86520" stop-opacity="0.3"/>
      <stop offset="50%"  stop-color="#E86520" stop-opacity="0.6"/>
      <stop offset="70%"  stop-color="#E86520" stop-opacity="0.3"/>
      <stop offset="100%" stop-color="#E86520" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="accentLine2Grad" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%"   stop-color="#E86520" stop-opacity="0"/>
      <stop offset="50%"  stop-color="#E86520" stop-opacity="0.2"/>
      <stop offset="100%" stop-color="#E86520" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="sepGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%"   stop-color="#E86520" stop-opacity="1"/>
      <stop offset="100%" stop-color="#E86520" stop-opacity="0"/>
    </linearGradient>
  `;

  // ------------------------------------------------------------------
  // L1: 무광 배경
  // 검은 카드, 그리드, 하단 엣지 (장식선/코너마크는 L3 Spot UV로 이동)
  // ------------------------------------------------------------------
  const l1 = `
    <rect x="0" y="0" width="${W}" height="${H}" ${fill(COLOR.black)}/>
    <rect x="0" y="0" width="${W}" height="${H}" fill="url(#gridpat)"/>
    <rect x="${W-200}" y="${H-2}" width="200" height="2" fill="url(#edgeBotGrad)"/>
  `;

  // ------------------------------------------------------------------
  // L2: 무광 텍스트
  // 태그라인, 이메일/웹, just watch., 구분선, 아이콘
  // ------------------------------------------------------------------
  const l2 = `
    <line x1="${sepX1}" y1="${sepY}" x2="${sepX2}" y2="${sepY}"
      stroke="url(#sepGrad)" stroke-width="1"/>
    ${tp(FONT.jb400, 'Autonomous AI Agent Platform', padL, tagBaseY, tagSz, { fill: COLOR.white35 })}
    <g transform="translate(${padL}, ${(emailLineCenterY - iconSz/2).toFixed(1)})" opacity="0.45">
      <rect x="0" y="2" width="14" height="10" rx="1.5"
        stroke="${COLOR.orange.hex}" stroke-width="1.5" fill="none"/>
      <path d="M0 4 L7 8 L14 4" stroke="${COLOR.orange.hex}" stroke-width="1.5" fill="none"/>
    </g>
    ${tp(FONT.jb400, 'ceo@ogenti.com', contactTextX, emailLineBaseY, 11.5, { fill: COLOR.white60 })}
    <g transform="translate(${padL}, ${(webLineCenterY - iconSz/2).toFixed(1)})" opacity="0.45">
      <circle cx="7" cy="7" r="6" stroke="${COLOR.orange.hex}" stroke-width="1.5" fill="none"/>
      <path d="M1 7 L13 7 M7 1 Q10.5 4 10.5 7 Q10.5 10 7 13 Q3.5 10 3.5 7 Q3.5 4 7 1"
        stroke="${COLOR.orange.hex}" stroke-width="1.5" fill="none"/>
    </g>
    ${tp(FONT.jb400, 'ogenti.com', contactTextX, webLineBaseY, 11.5, { fill: COLOR.white60 })}
    ${tp(FONT.jb500, jw_text, jw_x, jw_base, badgeSz1, { fill: COLOR.white60 })}
    ${tp(FONT.jb400, yw_text, yw_x, yw_base, badgeSz2, { fill: COLOR.white20 })}
  `;

  // ------------------------------------------------------------------
  // L3: 유광 Spot UV
  // 상단 오렌지 바, 로고마크, "ogenti", "Juwon Ha", "FOUNDER & CEO"
  // ------------------------------------------------------------------
  const l3 = `
    <rect x="0" y="0" width="${W}" height="3" fill="url(#edgeTopGrad)"/>
    <!-- 대각선 장식선 (Spot UV — 빛 받을 때 선이 번쩍) -->
    <line x1="${ax1}" y1="${ay1}" x2="${ax2.toFixed(1)}" y2="${ay2}"
      stroke="url(#accentLineGrad)" stroke-width="2" fill="none"/>
    <line x1="${(accentX+10).toFixed(1)}" y1="${ay1}" x2="${(ax2+10).toFixed(1)}" y2="${ay2}"
      stroke="url(#accentLine2Grad)" stroke-width="1" fill="none"/>
    <!-- 코너 마크 TL / BR (Spot UV) -->
    <path d="M${padL} ${padT*0.7} L${padL} ${padT*0.7+20} M${padL} ${padT*0.7} L${padL+20} ${padT*0.7}"
      stroke="#E86520" stroke-width="1" fill="none" stroke-opacity="0.25"
      color="icc-color(FOGRA39, 0, 0.565, 0.863, 0.09)"/>
    <path d="M${W-padR} ${H-padB*0.7} L${W-padR} ${H-padB*0.7-20} M${W-padR} ${H-padB*0.7} L${W-padR-20} ${H-padB*0.7}"
      stroke="#E86520" stroke-width="1" fill="none" stroke-opacity="0.25"
      color="icc-color(FOGRA39, 0, 0.565, 0.863, 0.09)"/>
    <!-- 로고마크 -->
    <g transform="translate(${logoMarkX}, ${logoMarkY}) scale(${44/48})">
      <circle cx="24" cy="24" r="14" stroke="${COLOR.white.hex}" stroke-width="2.5" fill="none"/>
      <path d="M18 30 L30 18" stroke="${COLOR.white.hex}" stroke-width="2.5"
        stroke-linecap="round" fill="none"/>
      <circle cx="30" cy="18" r="2.5" ${fill(COLOR.orange)}/>
    </g>
    ${tp(FONT.inter800, oText, logoTextX, oBaseY, oSz, { fill: COLOR.white })}
    <circle cx="${(dotX + dotR).toFixed(1)}" cy="${dotY.toFixed(1)}" r="${dotR}"
      ${fill(COLOR.orange)}/>
    ${tp(FONT.inter700, 'Juwon Ha', padL, nBaseY, nSz, { fill: COLOR.white })}
    ${tp(FONT.inter500, titleText, padL, tBaseY, tSz, { letterSpacing: 3, fill: COLOR.orange })}
  `;

  return { defs, l1, l2, l3 };
}

// ==========================================================================
// BACK CARD
// ==========================================================================
function buildBack() {
  const W = 1050, H = 600;
  const cx = W / 2;

  const logoSz   = 80;
  const groupH   = 80 + 28 + 58 + 28 + 16;
  const groupTopY = (H - groupH) / 2;

  const logoMarkY = groupTopY;

  const oSz    = 48;
  const oBaseY = logoMarkY + logoSz + 28 + asc(FONT.inter800, oSz);
  const oText  = 'ogenti';
  const oWidth = tw(FONT.inter800, oText, oSz);
  const dotR   = 7;
  const oX     = cx - (oWidth + 2 + dotR * 2 + 1) / 2;
  const dotX   = oX + oWidth + 2;
  const dotY   = oBaseY - oSz * 0.18;

  const sloganText = 'AUTONOMOUS AI AGENTS';
  const sloganSz   = 13;
  const sloganLS   = 4;
  const sloganW    = tw(FONT.jb400, sloganText, sloganSz, sloganLS);
  const sloganX    = cx - sloganW / 2;
  const sloganBaseY = oBaseY + oSz * 0.35 + 28 + asc(FONT.jb400, sloganSz);

  const defs = `
    <linearGradient id="backEdgeTop" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="25%" stop-color="#E86520" stop-opacity="0"/>
      <stop offset="50%" stop-color="#E86520" stop-opacity="1"/>
      <stop offset="75%" stop-color="#E86520" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="backEdgeBot" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="25%" stop-color="#E86520" stop-opacity="0"/>
      <stop offset="50%" stop-color="#E86520" stop-opacity="0.3"/>
      <stop offset="75%" stop-color="#E86520" stop-opacity="0"/>
    </linearGradient>
  `;

  // L1: 무광 배경 (코너마크는 L3 Spot UV로 이동)
  const l1 = `
    <rect x="0" y="0" width="${W}" height="${H}" ${fill(COLOR.black)}/>
    <rect x="0" y="0" width="${W}" height="${H}" fill="url(#gridpat)"/>
    <rect x="0" y="${H-2}" width="${W}" height="2" fill="url(#backEdgeBot)"/>
  `;

  // L2: 무광 텍스트  슬로건 (배경에 은은하게 깔림)
  const l2 = `
    ${tp(FONT.jb400, sloganText, sloganX, sloganBaseY, sloganSz, {
      letterSpacing: sloganLS, fill: COLOR.white35
    })}
  `;

  // L3: 유광 Spot UV — 상단 오렌지 바, 코너마크 4개, 로고마크, ogenti
  const l3 = `
    <rect x="0" y="0" width="${W}" height="3" fill="url(#backEdgeTop)"/>
    <!-- 코너 마크 4개 (Spot UV) -->
    <path d="M16 16 L16 36 M16 16 L36 16"
      stroke="#E86520" stroke-width="1" fill="none" stroke-opacity="0.22"
      color="icc-color(FOGRA39, 0, 0.565, 0.863, 0.09)"/>
    <path d="M${W-16} 16 L${W-16} 36 M${W-16} 16 L${W-36} 16"
      stroke="#E86520" stroke-width="1" fill="none" stroke-opacity="0.22"
      color="icc-color(FOGRA39, 0, 0.565, 0.863, 0.09)"/>
    <path d="M16 ${H-16} L16 ${H-36} M16 ${H-16} L36 ${H-16}"
      stroke="#E86520" stroke-width="1" fill="none" stroke-opacity="0.22"
      color="icc-color(FOGRA39, 0, 0.565, 0.863, 0.09)"/>
    <path d="M${W-16} ${H-16} L${W-16} ${H-36} M${W-16} ${H-16} L${W-36} ${H-16}"
      stroke="#E86520" stroke-width="1" fill="none" stroke-opacity="0.22"
      color="icc-color(FOGRA39, 0, 0.565, 0.863, 0.09)"/>
    <g transform="translate(${(cx - logoSz/2).toFixed(1)}, ${logoMarkY.toFixed(1)}) scale(${(logoSz/48).toFixed(4)})">
      <circle cx="24" cy="24" r="14" stroke="${COLOR.white.hex}" stroke-width="2.2" fill="none"/>
      <path d="M18 30 L30 18" stroke="${COLOR.white.hex}" stroke-width="2.2"
        stroke-linecap="round" fill="none"/>
      <circle cx="30" cy="18" r="2.8" ${fill(COLOR.orange)}/>
    </g>
    ${tp(FONT.inter800, oText, oX, oBaseY, oSz, { fill: COLOR.white })}
    <circle cx="${(dotX + dotR + 1).toFixed(1)}" cy="${dotY.toFixed(1)}" r="${dotR}"
      ${fill(COLOR.orange)}/>
  `;

  return { defs, l1, l2, l3 };
}

// --------------------------------------------------------------------------
function generateSVG(buildFn, label, outFile) {
  const data = buildFn();
  const svg = wrapSVG(data, label);
  const outPath = path.join(__dirname, '..', outFile);
  fs.writeFileSync(outPath, svg, 'utf8');
  const kb = (fs.statSync(outPath).size / 1024).toFixed(1);
  console.log(`  OK  ${outFile}  (${kb} KB)`);
}

console.log('\n-- Generating 3-layer print SVGs --');
generateSVG(buildFront, 'ogenti Business Card FRONT | L1 무광배경 / L2 무광텍스트 / L3 유광SpotUV', 'business_card_front.svg');
generateSVG(buildBack,  'ogenti Business Card BACK  | L1 무광배경 / L2 무광텍스트 / L3 유광SpotUV', 'business_card_back.svg');

console.log('\n  Layer guide:');
console.log('  l1-matte-bg   : 검은배경, 그리드, 장식선 => 무광 라미네이트');
console.log('  l2-matte-text : 태그라인, 연락처, just watch. => 무광 동일 판');
console.log('  l3-spot-uv    : ogenti, Juwon Ha, FOUNDER&CEO, 로고마크 => UV 유광');
console.log('\n  FOGRA39 | #E86520 = C0 M56.5 Y86.3 K9 | Trim 90x54mm | Bleed 3mm\n');
