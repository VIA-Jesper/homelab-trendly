# Implementation Note: LLM & AI Search Optimization

**Status:** Planned - implement when WordPress publishing pipeline is live
**Relates to:** ADR-010 (WP publishing deferred), article pipeline Phase 5

---

## Problem

AI assistants (ChatGPT, Perplexity, Claude, Gemini) increasingly answer product questions directly
and cite sources inline. If the site is not in their training data or crawl index, it will not be
cited regardless of content quality. Standard SEO (Google ranking) is necessary but not sufficient.

---

## What to implement

### 1. `/llms.txt` - machine-readable site index

A plain-text file at the domain root that lists pages an LLM should prioritize when crawling for
context. The format is a community proposal (Answer.AI, 2024) modeled on `robots.txt`.

**WordPress implementation:**

Option A - Static file (simplest):
```
wp-content/uploads/llms.txt  (served via rewrite rule)
```
Add to `.htaccess` or nginx config:
```nginx
location = /llms.txt {
    alias /var/www/html/llms.txt;
}
```

Option B - mu-plugin (recommended, auto-updates as content grows):
```php
// wp-content/mu-plugins/llms-txt.php
add_action('init', function () {
    if ($_SERVER['REQUEST_URI'] === '/llms.txt') {
        header('Content-Type: text/plain; charset=utf-8');
        $posts = get_posts(['post_type' => 'post', 'posts_per_page' => 100,
                            'post_status' => 'publish', 'orderby' => 'date', 'order' => 'DESC']);
        echo "# " . get_bloginfo('name') . "\n\n";
        echo "> " . get_bloginfo('description') . "\n\n";
        echo "## Articles\n\n";
        foreach ($posts as $post) {
            echo "- [" . $post->post_title . "](" . get_permalink($post) . ")\n";
        }
        exit;
    }
});
```

**File format:**
```
# TechBlog DK

> Danish affiliate tech reviews - robotics, smart home, consumer electronics.

## Articles

- [Dreame X50 Ultra Kombi Sort anmeldelse](https://techblog.dk/dreame-x50-ultra-kombi-sort-anmeldelse)
- [Bedste robotstøvsuger 2025](https://techblog.dk/bedste-robotstoevsuger-2025)
```

---

### 2. Schema.org structured data

LLMs weight pages with machine-readable structured data more heavily when deciding what to cite.
Add to every published article via a WP plugin (Yoast SEO, Rank Math, or custom output).

**For review articles (`single-product-review`):**
```json
{
  "@context": "https://schema.org",
  "@type": "Review",
  "itemReviewed": {
    "@type": "Product",
    "name": "Dreame X50 Ultra Kombi Sort",
    "brand": { "@type": "Brand", "name": "Dreame" }
  },
  "reviewRating": {
    "@type": "Rating",
    "ratingValue": "4",
    "bestRating": "5"
  },
  "author": { "@type": "Organization", "name": "TechBlog DK" },
  "datePublished": "2025-05-19",
  "publisher": { "@type": "Organization", "name": "TechBlog DK" }
}
```

**For roundup/hero articles:**
```json
{
  "@context": "https://schema.org",
  "@type": "Article",
  "headline": "...",
  "author": { "@type": "Organization", "name": "TechBlog DK" },
  "datePublished": "...",
  "dateModified": "...",
  "publisher": {
    "@type": "Organization",
    "name": "TechBlog DK",
    "logo": { "@type": "ImageObject", "url": "https://techblog.dk/logo.png" }
  }
}
```

**Implementation:** Inject via `wp-publisher.ts` when creating/updating the WP post.
The SEO payload from the article JSON (`seo.title`, `seo.description`, article type, product data)
maps directly onto the schema fields. Build a `buildJsonLd(articleJson, brief)` function in
`src/services/wp-publisher.ts` and add it to the post's `<head>` via custom field or Yoast API.

---

### 3. EEAT signals (Expertise, Authority, Trustworthiness)

LLMs and Google's EEAT framework both favor pages with clear authorship and editorial context.

- **Author byline:** Add a consistent author entity (organization or named author) to every post.
  Wire `author` into the WP post creation call in `wp-publisher.ts`.
- **Affiliate disclosure:** Already enforced by validator. Ensure it renders visibly above the fold,
  not buried in fine print.
- **Update dates:** Set `dateModified` when re-publishing an updated article. The pipeline
  already has `job_id` and timestamp - pass these through to WP.
- **Canonical URLs:** Ensure `rel="canonical"` is set. Yoast/Rank Math handles this if the slug
  is set correctly. The article JSON `seo.slug` is the source of truth.

---

### 4. `robots.txt` - allow AI crawlers

Some AI crawlers (GPTBot, ClaudeBot, PerplexityBot) are blocked by default `robots.txt` configs.
Ensure the following is NOT blocked:

```
User-agent: GPTBot
Allow: /

User-agent: ClaudeBot
Allow: /

User-agent: PerplexityBot
Allow: /
```

Check current `robots.txt` after WP is live. Many security plugins block all bots by default.

---

## Implementation order (when WP publishing goes live)

1. `robots.txt` audit - unblock AI crawlers (5 min, high impact)
2. Schema.org via `wp-publisher.ts` - wire `buildJsonLd()` into post creation
3. mu-plugin for `/llms.txt` - auto-updates as articles are published
4. EEAT signals - author entity, canonical, update dates

---

## What NOT to do

- Do not stuff keywords into `llms.txt` - it is a navigation index, not a content page.
- Do not add `noindex` to any published article - some caching/security plugins do this by mistake.
- Do not use `rel="nofollow"` on internal links - only on PriceRunner affiliate links.
