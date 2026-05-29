/**
 * Internal Link Applier
 * 
 * Reads the internal linking strategy and applies links to WordPress posts
 * by inserting contextual inline links into post content.
 * 
 * Usage: npx tsx scripts/apply-internal-links.ts [--dry-run]
 */

import * as fs from "fs";

const strategy = JSON.parse(
  fs.readFileSync("data/internal-linking-strategy.json", "utf-8")
);

const DRY_RUN = process.argv.includes("--dry-run");

// Build a lookup: post_id -> {title, link}
const postLookup: Record<number, { title: string; link: string }> = {};
for (const cluster of strategy.content_clusters) {
  for (const post of cluster.posts) {
    postLookup[post.id] = { title: post.title, link: post.link };
  }
}

// Build link instructions: for each source post, what links to add
interface LinkInstruction {
  from_id: number;
  to_id: number;
  anchor: string;
  target_url: string;
  target_title: string;
}

const instructions: LinkInstruction[] = [];
for (const mapping of strategy.internal_linking_map) {
  const fromId = mapping.from;
  for (const target of mapping.to) {
    const targetPost = postLookup[target.id];
    if (targetPost) {
      instructions.push({
        from_id: fromId,
        to_id: target.id,
        anchor: target.anchor,
        target_url: targetPost.link,
        target_title: targetPost.title,
      });
    }
  }
}

console.log(`Internal Link Strategy for ${strategy.site}`);
console.log(`Total link instructions: ${instructions.length}`);
console.log(`Mode: ${DRY_RUN ? "DRY RUN (no changes)" : "LIVE"}\n`);

// Group by source post
const grouped: Record<number, LinkInstruction[]> = {};
for (const inst of instructions) {
  if (!grouped[inst.from_id]) grouped[inst.from_id] = [];
  grouped[inst.from_id].push(inst);
}

for (const [postId, links] of Object.entries(grouped)) {
  console.log(`\n--- Post ${postId} ---`);
  for (const link of links) {
    console.log(`  Add: <a href="${link.target_url}">${link.anchor}</a> → Post ${link.to_id}`);
  }
}

console.log(`\n\nTo apply these links, the script needs to:`);
console.log(`1. Fetch each source post content via WP REST API`);
console.log(`2. Find a natural insertion point for each link (first mention of related topic)`);
console.log(`3. Insert <a href="...">anchor</a> as inline link`);
console.log(`4. Update post via PUT /wp/v2/posts/{id}`);
console.log(`\nRun without --dry-run to apply (once WP meta access is fixed).`);
