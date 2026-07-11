import { TemplateManager } from "@/components/templates/template-manager";
import { getSpawndClient } from "@/lib/server/client";

export const dynamic = "force-dynamic";

export default async function TemplatesPage() {
  const client = await getSpawndClient();
  const templates = await client.templates.list();

  return (
    <div className="p-6">
      <TemplateManager initialTemplates={templates} />
    </div>
  );
}
