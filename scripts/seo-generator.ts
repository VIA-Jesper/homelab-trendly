/**
 * SEO Metadata Generator — v2
 * 
 * Hard rules:
 * - No HTML entities (&nbsp;, &#8211;, &#8217;, etc.)
 * - No em/en dashes (– —)
 * - Focus kw 1-3 words, in title AND desc
 * - Title 40-65 chars with site suffix " | Hus for begyndere"
 * - Desc 120-155 chars
 */

import * as fs from "fs";

const postsRaw = JSON.parse(fs.readFileSync("/tmp/posts-for-seo.json", "utf-8"));

interface SeoMeta {
  id: number;
  title: string;
  slug: string;
  link: string;
  categories: number[];
  excerpt: string;
  seo_title: string;
  seo_metadesc: string;
  seo_focuskw: string;
}

function strip(text: string): string {
  return text
    .replace(/&#[0-9]+;/g, " ")
    .replace(/&[a-z]+;/gi, " ")
    .replace(/[–—]/g, "-")
    .replace(/\s+/g, " ")
    .trim();
}

const SUFFIX = " | Hus for begyndere";
const MAX_MAIN = 38; // 60 - suffix length

// Per-post hand-crafted metadata based on actual content
function generate(post: any): SeoMeta {
  const id = post.id;
  const title = strip(post.title);
  const slug = post.slug;
  const excerpt = strip(post.excerpt);
  const cats = post.categories;

  // Default auto-generation
  let focusKw = deriveFocus(slug, title);
  let seoTitle = buildTitle(title, focusKw);
  let seoDesc = buildDesc(title, focusKw, excerpt, cats);

  return { id, title, slug, link: post.link, categories: cats, excerpt: excerpt.substring(0, 200), seo_title: seoTitle, seo_metadesc: seoDesc, seo_focuskw: focusKw };
}

function deriveFocus(slug: string, title: string): string {
  const STOP = new Set(["den","det","der","til","med","fra","for","som","har","var","kan","ved","om","og","i","pa","af","de","du","din","dit","eller","men","at","en","et","ny","nye","bedste","saadan","foer","efter","over","under","eller","samt","selv","bl.a","fx","dvs","etc","mellem","uden","bag","op","ned","denne","disse","stor","store","nyeste","bedre"]);
  
  const words = slug.split("-").filter(w => w.length > 2 && !STOP.has(w.toLowerCase()) && !/^\d{4}$/.test(w));
  let kw = words.slice(0, 2).join(" ");
  
  if (!kw || kw.length < 3) {
    const tw = strip(title).split(/\s+/).filter(w => w.length > 2 && !STOP.has(w.toLowerCase()));
    kw = tw.slice(0, 2).join(" ");
  }
  
  return kw.toLowerCase().replace(/[^\w\sæøåÆØÅ-]/g, "").trim();
}

function buildTitle(rawTitle: string, focusKw: string): string {
  let main = strip(rawTitle).replace(/\b20\d{2}\b/g, "").replace(/\s*-\s*$/, "").replace(/\s+/g, " ").trim();
  
  // If short enough
  if (main.length <= MAX_MAIN) return main + SUFFIX;
  
  // Try cutting at colon
  const ci = main.indexOf(":");
  if (ci > 10 && ci <= MAX_MAIN) return main.substring(0, ci) + SUFFIX;
  
  // Try cutting at first dash
  const di = main.indexOf(" -");
  if (di > 10 && di <= MAX_MAIN) return main.substring(0, di) + SUFFIX;
  
  // Word truncate
  const words = main.split(/\s+/);
  let trunc = "";
  for (const w of words) {
    const next = trunc ? trunc + " " + w : w;
    if (next.length > MAX_MAIN) break;
    trunc = next;
  }
  if (trunc.length >= 10) return trunc + SUFFIX;
  
  // Fallback
  return focusKw.charAt(0).toUpperCase() + focusKw.slice(1) + SUFFIX;
}

function buildDesc(title: string, focusKw: string, excerpt: string, cats: number[]): string {
  // Clean excerpt
  let clean = strip(excerpt).replace(/[–—]/g, ",");
  const sentences = clean.split(/[.!?]+/).filter(s => s.trim().length > 15);
  
  // Build from excerpt sentences
  let desc = "";
  const s1 = sentences[0]?.trim();
  
  if (s1 && s1.length > 30 && s1.length < 100) {
    desc = s1.endsWith(".") ? s1 : s1 + ".";
  } else if (s1 && s1.length >= 100) {
    // Truncate at word boundary
    const words = s1.split(/\s+/);
    let t = "";
    for (const w of words) {
      const next = t ? t + " " + w : w;
      if (next.length > 90) break;
      t = next;
    }
    desc = t + ".";
  } else {
    desc = `Find de bedste ${focusKw} til dit hus.`;
  }

  // Add CTA with focus kw
  const ctas = [
    `Se vores anbefalinger og sammenlign ${focusKw}.`,
    `Las vores guide og find ${focusKw}.`,
    `Sammenlign ${focusKw} og priser.`,
    `Få hjælp til at vælge ${focusKw}.`,
    `Se valgene her.`,
  ];
  
  for (const cta of ctas) {
    if ((desc + " " + cta).length <= 155) {
      desc = desc + " " + cta;
      break;
    }
  }
  
  desc = desc.replace(/\.+$/, "") + ".";
  desc = strip(desc);
  
  if (desc.length > 155) desc = desc.substring(0, 152) + "...";
  if (desc.length < 110) desc = desc.replace(/\.$/, "") + " og spar penge.";
  
  return desc;
}

const results = postsRaw.map(generate);
fs.writeFileSync("/tmp/seo-metadata.json", JSON.stringify(results, null, 2));

console.log(`Generated SEO for ${results.length} posts\n`);
for (const r of results) {
  const kwInTitle = r.seo_title.toLowerCase().includes(r.seo_focuskw.toLowerCase());
  const kwInDesc = r.seo_metadesc.toLowerCase().includes(r.seo_focuskw.toLowerCase());
  const flags: string[] = [];
  if (!kwInTitle) flags.push("kw∉title");
  if (!kwInDesc) flags.push("kw∉desc");
  if (r.seo_title.length < 40) flags.push("title<40");
  if (r.seo_title.length > 65) flags.push("title>65");
  if (r.seo_metadesc.length < 100) flags.push("desc<100");
  if (r.seo_metadesc.length > 160) flags.push("desc>160");
  if (/[–—]/.test(r.seo_title) || /[–—]/.test(r.seo_metadesc)) flags.push("dashes");
  if (/&#|&[a-z]+;/.test(r.seo_title) || /&#|&[a-z]+;/.test(r.seo_metadesc)) flags.push("entities");
  
  const status = flags.length === 0 ? "✅" : "⚠️";
  console.log(`${status} ID:${r.id} [${flags.join(", ") || "ok"}]`);
  console.log(`  T(${r.seo_title.length}): ${r.seo_title}`);
  console.log(`  D(${r.seo_metadesc.length}): ${r.seo_metadesc}`);
  console.log(`  K: ${r.seo_focuskw}`);
  console.log();
}
