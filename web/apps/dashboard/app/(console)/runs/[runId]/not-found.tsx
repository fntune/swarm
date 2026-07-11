import { EmptyState } from "@spawnd/ui/components/empty-state";
import { SearchXIcon } from "lucide-react";

export default function RunNotFound() {
  return (
    <div className="p-6">
      <EmptyState
        icon={SearchXIcon}
        title="Run not found"
        description="This run id does not exist in the deployed backend."
      />
    </div>
  );
}
