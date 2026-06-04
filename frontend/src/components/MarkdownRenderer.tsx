type Props = {
  content: string;
};

export default function MarkdownRenderer({ content }: Props) {
  const lines = content.split(/\r?\n/);
  const blocks: JSX.Element[] = [];
  let listItems: string[] = [];

  function flushList(key: string) {
    if (listItems.length === 0) return;
    blocks.push(
      <ul className="markdown-list" key={key}>
        {listItems.map((item, index) => <li key={`${key}-${index}`}>{renderInline(item)}</li>)}
      </ul>
    );
    listItems = [];
  }

  lines.forEach((rawLine, index) => {
    const line = rawLine.trim();
    if (!line) {
      flushList(`list-${index}`);
      return;
    }
    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      flushList(`list-${index}`);
      const level = Math.min(heading[1].length, 3);
      const Tag = (`h${level + 2}` as keyof JSX.IntrinsicElements);
      blocks.push(<Tag className="markdown-heading" key={`heading-${index}`}>{renderInline(heading[2])}</Tag>);
      return;
    }
    const list = line.match(/^[-*]\s+(.+)$/);
    if (list) {
      listItems.push(list[1]);
      return;
    }
    flushList(`list-${index}`);
    blocks.push(<p key={`p-${index}`}>{renderInline(line)}</p>);
  });
  flushList("list-end");

  return <div className="markdown-rendered">{blocks}</div>;
}

function renderInline(text: string): JSX.Element[] {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={`${part}-${index}`}>{part.slice(2, -2)}</strong>;
    }
    return <span key={`${part}-${index}`}>{part}</span>;
  });
}
