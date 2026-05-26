# Widget & Affiliate Link System — Reference Document

This document captures how Trendly generates PriceRunner affiliate widgets and inserts them into markdown article content. Intended for reuse in another project without rediscovering the logic.

---

## Overview

The widget system does three things:

1. **Detects** where products are mentioned in markdown content (via `ProductMentionDetector`)
2. **Inserts** embeddable PriceRunner price-comparison widgets after relevant paragraphs (via `SmartWidgetInserter`)
3. **Converts** plain product name mentions into affiliate links inline (also `SmartWidgetInserter`)

The entry point is `SmartWidgetInserter.InsertWidgetsAndLinks()`. It takes markdown in, returns markdown+HTML out.

---

## The Widget HTML

The widget itself is two parts — a container `<div>` and an async `<script>` tag that PriceRunner's CDN fills in:

```html
<div id="pr-product-widget-{guid}" style="display: block; width: 100%"></div>

<script type="text/javascript"
  src="https://api.pricerunner.com/publisher-widgets/{country}/product.js?onlyInStock=true&offerOrigin=NATIONAL&offerLimit=3&productId={productId}&partnerId={partnerId}&widgetId=pr-product-widget-{guid}"
  async>
</script>

<div style="display: inline-block">
  <a href="{absoluteProductUrl}" rel="sponsored">
    <p style="font: 14px 'Klarna Text', Helvetica, sans-serif; font-style: italic; color: var(--grayscale100); text-decoration: underline;">
       Annonce i samarbejde med <span style="font-weight:bold">PriceRunner</span>
    </p>
  </a>
</div>
```

### Widget Script Parameters

| Param | Example | Notes |
|---|---|---|
| `country` | `dk` | Lowercase country code in the URL path |
| `onlyInStock` | `true` | Show only in-stock offers |
| `offerOrigin` | `NATIONAL` | `NATIONAL` or `INTERNATIONAL` |
| `offerLimit` | `3` | Max number of offers to show |
| `productId` | `3741515` | Numeric PriceRunner product ID (from scraper results) |
| `partnerId` | `adrunner_dk_husforbegyndere` | Your affiliate partner ID from PriceRunner |
| `widgetId` | `pr-product-widget-{guid}` | Matches the container div ID — must be unique per page |

### Important Notes

- `productId` is the **numeric** PriceRunner product ID from the scraper's `id` field (e.g., `"3741515"`). This is **not** the URL slug or the full path.
- The attribution link (`rel="sponsored"`) at the bottom is **required** by PriceRunner's affiliate terms. The Danish text "Annonce i samarbejde med PriceRunner" means "Advertisement in collaboration with PriceRunner".
- The widget div ID must be globally unique — use a GUID per widget instance.
- The product URL in the attribution link must be **absolute** (not relative). If you get a relative URL from the scraper (`/pl/...`), prepend the country base URL.

### Fallback (no widget — simple link instead)

When a `productId` or `partnerId` is missing, fall back to a plain button link:

```html
<p><a href="{absoluteProductUrl}" rel="sponsored" class="btn-primary">Se pris på {productName}</a></p>
```

---

## Product Image HTML

Before each widget, an optional product image is prepended:

```html
<figure class="product-image" style="margin: 1.5em 0; text-align: center;">
<img src="{absoluteImageUrl}" alt="{productName} - {keyword or brand}" loading="lazy" style="max-width: 100%; height: auto; border-radius: 8px;" />
</figure>
```

### Alt Text Logic

Priority order:
1. `{productName} - {article keyword}` — best for SEO (keyword-rich)
2. `{productName} - {brandName}` — if no keyword available
3. `{productName}` — fallback

Alt text is HTML-escaped (`"` → `&quot;`, `&` → `&amp;`, etc.).

### Image URL Resolution

- If the image URL starts with `/`, prepend the country base URL
- Country base URL mapping: `DK` → `https://www.pricerunner.dk`, `SE` → `https://www.pricerunner.se`, `NO` → `https://www.pricerunner.no`, `UK` → `https://www.pricerunner.co.uk`
- The `<figure>` block must be wrapped with blank lines (`\n\n...\n\n`) so that Markdig (the markdown parser) treats it as a block element, not inline text

---

## Inline Affiliate Links

Every non-heading mention of a product name (up to 2 per product) is also converted to an affiliate link:

```html
<a href="{absoluteProductUrl}?partnerId={partnerId}" rel="sponsored" class="product-link">{mentionText}</a>
```

- Max **2 links** per product (additional mentions are left as plain text)
- Mentions **inside headings** are skipped (never linked)
- `partnerId` is appended as a query param: `?partnerId=...` (or `&partnerId=...` if URL already has params)

---

## Full Insertion Flow

```
InsertWidgetsAndLinks(markdownContent, products, siteId, maxWidgets, keyword?)
│
├─ 1. ProductMentionDetector.DetectMentions()
│       → finds all product name occurrences with position + context
│
├─ 2. PASS 1 — Widget Insertion
│       For each product (in order):
│         Find first mention → calculate widget position (2 body-text paragraphs after)
│         If position is free → insert widget HTML at that position
│         Track: 1 widget max per product, maxWidgets global cap
│
├─ 3. PASS 2 — Link Conversion
│       For each product mention (non-heading):
│         Replace mention text with <a> link
│         Cap at 2 links per product
│
└─ 4. Apply all insertions in reverse index order (to preserve earlier indices)
       Return modified content + WidgetInsertionReport
```

---

## Widget Placement Algorithm

Widgets are NOT inserted immediately after the mention. Instead they're placed **after the 2nd body-text paragraph break** following the mention. This keeps widgets away from headings and list items.

### Structural elements skipped during positioning

The inserter skips paragraph breaks that are adjacent to any of these:
- Markdown headings (`# `, `## `, `### `)
- HTML blocks (`<figure`, `<div`, `<table`, etc.)
- Bullet list items (`- `, `* `, `+ `)
- Numbered list items (`1. `, `2. `, etc.)

A break is skipped if **the line before it** or **the line after it** is structural.

### Safety valve

If 4+ consecutive structural breaks are encountered after at least one body-text break was found, the algorithm falls back to the last body-text break position. This prevents widgets being pushed to the end of article-dense articles (lots of headings + bullet lists).

### Edge case

If no body-text paragraph break exists after the mention at all, the widget is inserted at end-of-content.

---

## Product Mention Detection

### Search Patterns (per product)

Three patterns are tried in this order:
1. **Full product name** (e.g., `"Mitsubishi Ecodan 8kW"`) — confidence 100
2. **Brand + first significant model word** (word > 3 chars, e.g., `"Mitsubishi Ecodan"`) — confidence 90
3. **Brand only** (if brand > 4 chars and pattern 2 wasn't generated) — confidence 50

All patterns use **word boundary regex** (`\bpattern\b`) and are **case-insensitive**.

### Confidence Scoring

| Match Type | Score |
|---|---|
| Exact full name match | 100 |
| Contains brand + ≥3 more chars | 90 |
| Contains model part's first word | 70 |
| Brand only | 50 |
| Partial / contains pattern | 30 |

### Deduplication

Two passes of deduplication:
1. **Same position**: if two products match at the exact same index range, keep highest confidence
2. **Overlapping ranges**: if ranges overlap, keep highest confidence and discard the other

### Heading Detection

`MentionContext.IsInHeading` is `true` when the section heading text contains the matched mention text. Heading mentions are excluded from link conversion (but widgets can still be placed based on them).

---

## Markdown Section Parser

Content is split into `MarkdownSection` objects before mention detection. Each section corresponds to one `# / ## / ###` heading block.

```
MarkdownSection {
    Heading: "Vigtigste egenskaber",
    HeadingLevel: 2,
    StartIndex: 142,    // char offset in original markdown
    EndIndex: 310,
    Content: "Her er...",   // trimmed section body
    Paragraphs: [...],  // split on \n\n
    TrimOffset: 2       // chars trimmed from start (for absolute index calculation)
}
```

When no headings are found, the entire document is one section with `Heading: "Content"` and `HeadingLevel: 0`.

Mention `StartIndex`/`EndIndex` are calculated as:
```
section.StartIndex + section.TrimOffset + match.Index
```

---

## Configuration

Widget generation requires a `partnerId` per site. This is stored in `appsettings.json`:

```json
{
  "PriceRunner": {
    "Sites": {
      "dk-husforbegyndere": {
        "PartnerId": "adrunner_dk_husforbegyndere",
        "Country": "DK"
      },
      "default": {
        "PartnerId": "",
        "Country": "DK"
      }
    }
  }
}
```

`GetPartnerIdForSite(siteId)` does an exact match first, then falls back to `"default"`.

---

## Data Types

### ProductCandidate

The input model for each product to embed:

```csharp
record ProductCandidate(
    Guid ProductId,           // Internal ID (for dedup tracking)
    string Name,              // Display name — used for mention detection
    string? Brand = null,     // Brand name — used for mention pattern 2/3
    string? Category = null,
    string? PriceRunnerUrl = null,        // Can be relative (/pl/...) or absolute
    string? PriceRunnerProductId = null,  // Numeric ID for widget script (e.g., "3741515")
    string? ImageUrl = null,              // Can be relative or absolute
    decimal? MinPrice = null,
    string? Currency = null,
    string? Availability = null,
    double? Rating = null
);
```

### WidgetInsertionReport

Returned after `InsertWidgetsAndLinks()`:

```csharp
record WidgetInsertionReport(
    int WidgetsInserted,
    int LinksInserted,
    List<ProductCandidate> ProductsNotMentioned,   // Products with 0 mentions
    Dictionary<ProductCandidate, int> MentionCounts,
    bool ShouldDiscard,          // true if any product was not mentioned
    List<string> ProductsWithWidgets  // PriceRunnerProductId for each product that got a widget
);
```

`ShouldDiscard` is used by the pipeline to flag articles that don't mention all products — they're candidates for regeneration.

---

## Minimal Standalone Implementation

```csharp
using System.Text;
using System.Text.RegularExpressions;

public class SimpleWidgetInserter
{
    private readonly string _partnerId;
    private readonly string _country;

    public SimpleWidgetInserter(string partnerId, string country = "DK")
    {
        _partnerId = partnerId;
        _country = country.ToUpper();
    }

    public string InsertWidgets(string markdown, List<(string productId, string productName, string productUrl, string? imageUrl)> products, int maxWidgets = 3)
    {
        var content = new StringBuilder(markdown);
        var widgetsInserted = 0;
        var insertions = new List<(int index, string html)>();

        foreach (var (productId, productName, productUrl, imageUrl) in products)
        {
            if (widgetsInserted >= maxWidgets) break;

            // Find mention
            var mentionIdx = markdown.IndexOf(productName, StringComparison.OrdinalIgnoreCase);
            if (mentionIdx == -1) continue;

            // Find widget insertion position (after 2nd body paragraph break)
            var position = FindWidgetPosition(markdown, mentionIdx + productName.Length);

            // Build widget HTML
            var widgetHtml = BuildWidgetBlock(productId, productName, productUrl, imageUrl);
            insertions.Add((position, widgetHtml));
            widgetsInserted++;
        }

        // Apply in reverse to preserve indices
        foreach (var (index, html) in insertions.OrderByDescending(x => x.index))
            content.Insert(index, html + "\n\n");

        return content.ToString();
    }

    private int FindWidgetPosition(string content, int searchFrom)
    {
        int breaksFound = 0;
        int pos = searchFrom;

        while (breaksFound < 2)
        {
            var nextBreak = content.IndexOf("\n\n", pos);
            if (nextBreak == -1) return content.Length;

            var afterBreak = nextBreak + 2;

            // Skip structural lines
            if (IsStructural(content, afterBreak) || IsStructuralBefore(content, nextBreak))
            {
                pos = afterBreak;
                continue;
            }

            breaksFound++;
            if (breaksFound >= 2) return nextBreak;
            pos = afterBreak;
        }

        return content.Length;
    }

    private static bool IsStructural(string content, int pos)
    {
        if (pos >= content.Length) return false;
        while (pos < content.Length && (content[pos] == ' ' || content[pos] == '\t')) pos++;
        if (pos >= content.Length) return false;
        if (content[pos] == '#') return true;
        if (content[pos] == '<' && pos + 1 < content.Length && char.IsLetter(content[pos + 1])) return true;
        if ((content[pos] == '-' || content[pos] == '*') && pos + 1 < content.Length && content[pos + 1] == ' ') return true;
        return false;
    }

    private static bool IsStructuralBefore(string content, int breakPos)
    {
        if (breakPos <= 0) return false;
        int lineEnd = breakPos - 1;
        if (lineEnd >= 0 && content[lineEnd] == '\r') lineEnd--;
        if (lineEnd < 0) return false;
        int lineStart = lineEnd;
        while (lineStart > 0 && content[lineStart - 1] != '\n') lineStart--;
        return IsStructural(content, lineStart);
    }

    private string BuildWidgetBlock(string productId, string productName, string productUrl, string? imageUrl)
    {
        var sb = new StringBuilder();

        // Ensure absolute URL
        if (productUrl.StartsWith("/"))
            productUrl = GetBaseUrl() + productUrl;

        // Optional image
        if (!string.IsNullOrWhiteSpace(imageUrl))
        {
            if (imageUrl.StartsWith("/")) imageUrl = GetBaseUrl() + imageUrl;
            sb.AppendLine($"\n\n<figure class=\"product-image\" style=\"margin: 1.5em 0; text-align: center;\">");
            sb.AppendLine($"<img src=\"{imageUrl}\" alt=\"{System.Net.WebUtility.HtmlEncode(productName)}\" loading=\"lazy\" style=\"max-width: 100%; height: auto; border-radius: 8px;\" />");
            sb.AppendLine("</figure>\n\n");
        }

        // Widget
        var widgetId = $"pr-product-widget-{Guid.NewGuid():N}";
        var country = _country.ToLower();
        sb.AppendLine($"<div id=\"{widgetId}\" style=\"display: block; width: 100%\"></div>");
        sb.AppendLine();
        sb.AppendLine($"<script type=\"text/javascript\"");
        sb.AppendLine($"  src=\"https://api.pricerunner.com/publisher-widgets/{country}/product.js?onlyInStock=true&offerOrigin=NATIONAL&offerLimit=3&productId={productId}&partnerId={_partnerId}&widgetId={widgetId}\"");
        sb.AppendLine($"  async>");
        sb.AppendLine("</script>");
        sb.AppendLine();

        // Required attribution link
        sb.AppendLine("<div style=\"display: inline-block\">");
        sb.AppendLine($"  <a href=\"{productUrl}\" rel=\"sponsored\">");
        sb.AppendLine("    <p style=\"font: 14px 'Klarna Text', Helvetica, sans-serif; font-style: italic; color: var(--grayscale100); text-decoration: underline;\">");
        sb.AppendLine("       Annonce i samarbejde med <span style=\"font-weight:bold\">PriceRunner</span>");
        sb.AppendLine("    </p>");
        sb.AppendLine("  </a>");
        sb.AppendLine("</div>");

        return sb.ToString();
    }

    private string GetBaseUrl() => _country switch
    {
        "SE" => "https://www.pricerunner.se",
        "NO" => "https://www.pricerunner.no",
        "UK" => "https://www.pricerunner.co.uk",
        _ => "https://www.pricerunner.dk"
    };
}
```

### Usage

```csharp
var inserter = new SimpleWidgetInserter(partnerId: "adrunner_dk_husforbegyndere", country: "DK");

var products = new List<(string, string, string, string?)>
{
    ("3741515", "Mitsubishi Ecodan 8kW", "/pl/3741515/Varmepumpe", "https://images.pricerunner.com/product/3741515.jpg"),
    ("9872341", "Daikin Altherma", "/pl/9872341/Varmepumpe", null)
};

var result = inserter.InsertWidgets(markdownContent, products, maxWidgets: 2);
```

---

## Key Constraints & Gotchas

1. **productId must be the numeric ID** — not the URL slug. From the scraper, use `product.Id` (e.g., `"3741515"`), not the `url` field.

2. **Widget div ID must be unique per rendered page** — if you embed multiple widgets, each needs a distinct GUID. The script uses it to find its container.

3. **Attribution link is required** — PriceRunner's terms require the `rel="sponsored"` attribution link below each widget.

4. **Relative URLs must be made absolute** — both product URLs and image URLs from the PriceRunner scraper may be relative (`/pl/...`). Always prepend the base URL before inserting into HTML attributes.

5. **Image HTML needs surrounding blank lines** — the `<figure>` block must have `\n\n` before and after it so markdown parsers (Markdig) treat it as a block element and don't wrap it in `<p>` tags.

6. **Insertions must be applied in reverse index order** — if you're inserting multiple widgets/links into the same string, apply them from the end of the string backwards. Otherwise early insertions shift the indices of later ones.

7. **Max 2 inline links per product** — converting every mention to a link looks spammy and hurts SEO. Cap at 2.

8. **Never link mentions in headings** — heading links break SEO structure and look wrong visually.
