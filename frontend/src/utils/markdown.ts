const KEYWORDS = new Set([
  "async",
  "await",
  "break",
  "case",
  "catch",
  "class",
  "const",
  "continue",
  "def",
  "delete",
  "do",
  "else",
  "export",
  "extends",
  "false",
  "finally",
  "for",
  "from",
  "function",
  "if",
  "import",
  "in",
  "interface",
  "let",
  "new",
  "none",
  "null",
  "pass",
  "return",
  "static",
  "switch",
  "throw",
  "true",
  "try",
  "type",
  "undefined",
  "var",
  "while",
]);
const CODE_TOKEN_PATTERN =
  /(\/\/[^\n]*|#[^\n]*|\/\*[\s\S]*?\*\/|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\b\d+(?:\.\d+)?\b|\b[A-Za-z_$][\w$]*\b)/g;

/** Escape source text before any HTML markup is generated. */
export function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

/** Render a safe, practical subset of Markdown used by chat answers. */
export function renderMarkdown(source: string): string {
  const lines = source.replaceAll("\r\n", "\n").split("\n");
  const output: string[] = [];
  const paragraph: string[] = [];
  let listType: "ol" | "ul" | null = null;
  let inCode = false;
  let codeLanguage = "text";
  let codeLines: string[] = [];

  /** Flush buffered paragraph text. */
  const flushParagraph = (): void => {
    if (paragraph.length > 0) {
      output.push(`<p>${renderInline(paragraph.join(" "))}</p>`);
      paragraph.length = 0;
    }
  };

  /** Close the active Markdown list. */
  const closeList = (): void => {
    if (listType !== null) {
      output.push(`</${listType}>`);
      listType = null;
    }
  };

  /** Flush a fenced code block with safe syntax highlighting. */
  const flushCode = (): void => {
    const language = normalizeLanguage(codeLanguage);
    output.push(
      `<pre class="code-block"><div class="code-header">${escapeHtml(language)}</div>` +
        `<code class="language-${escapeHtml(language)}">${highlightCode(codeLines.join("\n"))}</code></pre>`,
    );
    codeLines = [];
  };

  for (const line of lines) {
    const fence = line.match(/^```([\w+-]*)\s*$/);
    if (fence !== null) {
      if (inCode) {
        flushCode();
        inCode = false;
      } else {
        flushParagraph();
        closeList();
        codeLanguage = fence[1] || "text";
        inCode = true;
      }
      continue;
    }

    if (inCode) {
      codeLines.push(line);
      continue;
    }

    if (line.trim() === "") {
      flushParagraph();
      closeList();
      continue;
    }

    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading !== null) {
      flushParagraph();
      closeList();
      const level = heading[1].length;
      output.push(`<h${level}>${renderInline(heading[2])}</h${level}>`);
      continue;
    }

    const quote = line.match(/^>\s?(.*)$/);
    if (quote !== null) {
      flushParagraph();
      closeList();
      output.push(`<blockquote>${renderInline(quote[1])}</blockquote>`);
      continue;
    }

    const unorderedItem = line.match(/^[-*+]\s+(.+)$/);
    const orderedItem = line.match(/^\d+[.)]\s+(.+)$/);
    if (unorderedItem !== null || orderedItem !== null) {
      flushParagraph();
      const nextListType = unorderedItem !== null ? "ul" : "ol";
      if (listType !== nextListType) {
        closeList();
        listType = nextListType;
        output.push(`<${listType}>`);
      }
      const item = unorderedItem?.[1] ?? orderedItem?.[1] ?? "";
      output.push(`<li>${renderInline(item)}</li>`);
      continue;
    }

    paragraph.push(line.trim());
  }

  if (inCode) {
    flushCode();
  }
  flushParagraph();
  closeList();
  return output.join("\n");
}

/** Render safe inline code, emphasis, and external links. */
function renderInline(source: string): string {
  const inlineCode: string[] = [];
  let rendered = escapeHtml(source).replace(/`([^`\n]+)`/g, (_match, code: string) => {
    const index = inlineCode.push(`<code>${code}</code>`) - 1;
    return `\u0000${index}\u0000`;
  });
  rendered = rendered
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/__([^_]+)__/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>")
    .replace(
      /\[([^\]]+)]\((https?:\/\/[^\s)]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>',
    )
    .replace(/\[(S\d+)]/gi, (_match, citationId: string) => {
      const normalizedId = citationId.toUpperCase();
      return (
        `<button type="button" class="citation-reference" ` +
        `data-citation-id="${normalizedId}">[${normalizedId}]</button>`
      );
    });
  return rendered.replace(/\u0000(\d+)\u0000/g, (_match, index: string) =>
    inlineCode[Number(index)] ?? "",
  );
}

/** Highlight common code tokens while preserving escaped source text. */
function highlightCode(source: string): string {
  let cursor = 0;
  const output: string[] = [];
  for (const match of source.matchAll(CODE_TOKEN_PATTERN)) {
    const index = match.index ?? 0;
    const token = match[0];
    output.push(escapeHtml(source.slice(cursor, index)));
    output.push(`<span class="token-${tokenType(token)}">${escapeHtml(token)}</span>`);
    cursor = index + token.length;
  }
  output.push(escapeHtml(source.slice(cursor)));
  return output.join("");
}

/** Classify a source token for CSS highlighting. */
function tokenType(token: string): "comment" | "keyword" | "number" | "plain" | "string" {
  if (token.startsWith("//") || token.startsWith("#") || token.startsWith("/*")) {
    return "comment";
  }
  if (token.startsWith('"') || token.startsWith("'")) {
    return "string";
  }
  if (/^\d/.test(token)) {
    return "number";
  }
  if (KEYWORDS.has(token.toLowerCase())) {
    return "keyword";
  }
  return "plain";
}

/** Normalize a fenced language identifier for display and CSS classes. */
function normalizeLanguage(language: string): string {
  return language.trim().toLowerCase().replace(/[^a-z0-9_+-]/g, "") || "text";
}
