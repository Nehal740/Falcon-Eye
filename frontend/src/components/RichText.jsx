// Shows an assistant answer as tidy paragraphs, numbered steps, bullets, **bold** and `code`.
// It builds React elements itself (no HTML is injected), so answers can never run scripts.

function inline(text, key) {
  const parts = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0;
  let n = 0;
  let m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const token = m[0];
    parts.push(token.startsWith('**')
      ? <strong key={`${key}-${n++}`}>{token.slice(2, -2)}</strong>
      : <code key={`${key}-${n++}`}>{token.slice(1, -1)}</code>);
    last = m.index + token.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

export function parseBlocks(text) {
  const blocks = [];
  let list = null;
  const flush = () => { if (list) { blocks.push(list); list = null; } };
  String(text || '').replace(/\r/g, '').split('\n').forEach((raw) => {
    const line = raw.trim();
    const ordered = line.match(/^\d+[.)]\s+(.*)/);
    const bullet = line.match(/^[-*•]\s+(.*)/);
    if (ordered || bullet) {
      const type = ordered ? 'ol' : 'ul';
      if (!list || list.type !== type) { flush(); list = { type, items: [] }; }
      list.items.push((ordered || bullet)[1]);
    } else if (!line) {
      flush();
    } else {
      flush();
      const heading = line.match(/^#{1,6}\s+(.*)/);
      blocks.push(heading ? { type: 'h', text: heading[1] } : { type: 'p', text: line });
    }
  });
  flush();
  return blocks;
}

export default function RichText({ text }) {
  return (
    <div className="rich">
      {parseBlocks(text).map((b, i) => {
        if (b.type === 'ol') return <ol key={i}>{b.items.map((t, j) => <li key={j}>{inline(t, `${i}-${j}`)}</li>)}</ol>;
        if (b.type === 'ul') return <ul key={i}>{b.items.map((t, j) => <li key={j}>{inline(t, `${i}-${j}`)}</li>)}</ul>;
        if (b.type === 'h') return <p key={i}><strong>{inline(b.text, i)}</strong></p>;
        return <p key={i}>{inline(b.text, i)}</p>;
      })}
    </div>
  );
}
