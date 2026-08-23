import type { NewsContent } from '@krutrim_agent/shared-types';
import { Badge, Card, CardContent, CardTitle } from '@krutrim_agent/ui';

export function NewsView({ content }: { content: string }) {
  let data: NewsContent;
  try {
    data = JSON.parse(content);
  } catch {
    return <p className="text-sm text-muted-foreground">Couldn't parse news data.</p>;
  }
  if (!data.items?.length) {
    return <p className="text-sm text-muted-foreground">No items.</p>;
  }

  return (
    <div className="flex flex-col gap-3">
      {data.items.map((item) => (
        <Card key={item.headline}>
          <Badge variant="accent" className="mb-2">
            {item.source}
          </Badge>
          <CardTitle className="mb-1 text-sm">
            {item.url ? (
              <a href={item.url} target="_blank" rel="noreferrer" className="hover:text-primary">
                {item.headline}
              </a>
            ) : (
              item.headline
            )}
          </CardTitle>
          <CardContent>{item.summary}</CardContent>
        </Card>
      ))}
    </div>
  );
}
