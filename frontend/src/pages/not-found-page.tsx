import { Link } from "react-router";

import { Button } from "@/components/ui/button";

export function NotFoundPage() {
  return (
    <div className="flex flex-col items-start gap-4">
      <h1 className="text-2xl font-semibold">Page not found</h1>
      <p className="text-muted-foreground">That page doesn't exist.</p>
      <Button asChild variant="outline">
        <Link to="/">Back to system status</Link>
      </Button>
    </div>
  );
}
