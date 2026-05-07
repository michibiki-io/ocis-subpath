# CommonMark Smoke Test

This file is intended to test basic CommonMark rendering.

It includes headings, paragraphs, emphasis, lists, links, images, block quotes,
code blocks, inline HTML, escaping, entities, and thematic breaks.

---

## 1. Paragraphs and line breaks

This is a normal paragraph.
A single newline should not create a hard line break.

This line ends with two spaces.  
This should appear on the next line.

This line uses a backslash.\
This should also appear on the next line.

## 2. Emphasis

This is *emphasis*.

This is _also emphasis_.

This is **strong emphasis**.

This is __also strong emphasis__.

This is ***strong emphasis and emphasis***.

This tests punctuation: **strong**, *emphasis*, and normal text.

## 3. Inline code

Use `kubectl get pods` to list pods.

Inline code should preserve symbols like `<html>`, `&&`, `|`, and `$PATH`.

## 4. Links

This is an inline link to [CommonMark](https://commonmark.org/).

This is a reference-style link to [the specification][spec].

[spec]: https://spec.commonmark.org/

## 5. Images

This is an image syntax example:

![Markdown logo alt text](https://commonmark.org/help/images/favicon.png)

If the renderer blocks remote images, the alt text should still be handled safely.

## 6. Block quotes

> This is a block quote.
>
> It contains multiple paragraphs.
>
> - It can contain lists.
> - It can contain **emphasis**.
>
> > This is a nested block quote.

## 7. Unordered lists

- First item
- Second item
  - Nested item A
  - Nested item B
- Third item

## 8. Ordered lists

1. First item
2. Second item
3. Third item

Start number test:

7. This list starts at seven.
8. The next item should follow.

## 9. Loose list

- This is the first loose item.

  It has a second paragraph.

- This is the second loose item.

  It also has a second paragraph.

## 10. Code block by indentation

    apiVersion: v1
    kind: ConfigMap
    metadata:
      name: example

## 11. Fenced code block

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: markdown-preview-test
spec:
  replicas: 1
```

```bash
set -euo pipefail

echo "Hello, CommonMark"
curl -I https://commonmark.org/
```

## 12. Thematic breaks

Three hyphens:

---

Three asterisks:

***

Three underscores:

___

## 13. Escaping

\*This should not be emphasis.\*

\# This should not be a heading.

\[This should not be a link\](https://example.com)

Backslash escaping should be visible in the rendered result.

## 14. Entities

HTML entity test:

- `&amp;` should render as ampersand.
- `&lt;` should render as less-than.
- `&gt;` should render as greater-than.
- `&quot;` should render as quotation mark.

Actual entity rendering:

&copy; &amp; &lt; &gt; &quot;

## 15. Inline HTML

<div>
  <strong>This is inline HTML.</strong>
</div>

CommonMark allows raw HTML, but some preview systems sanitize it.

<script>
console.log("This should normally be sanitized or blocked by safe renderers.");
</script>

## 16. Autolink

<https://commonmark.org/>

<user@example.com>

## 17. Special characters

Japanese text:

これは日本語の Markdown 表示テストです。

Emoji:

✅ 🚀 📄

Symbols:

`~!@#$%^&*()_+-={}[]|\:;"'<>,.?/`

## 18. Long paragraph

This is a long paragraph intended to check wrapping behavior in the preview area. It should wrap naturally without horizontal scrolling unless the renderer or CSS intentionally applies a fixed-width layout. The goal is to verify that normal prose remains readable in the preview pane.

## 19. Mixed content

> ### Quoted heading
>
> ```text
> code block inside quote
> ```
>
> 1. quoted ordered item
> 2. another quoted ordered item

## 20. End

If this line is visible, the Markdown file was rendered to the end.
