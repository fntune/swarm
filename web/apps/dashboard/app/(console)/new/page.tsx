import { Tabs, TabsContent, TabsList, TabsTrigger } from "@spawnd/ui/components/ui/tabs";

import { PlanComposer } from "@/components/submit/plan-composer";
import { TemplateRunner } from "@/components/submit/template-runner";
import { getSpawndClient } from "@/lib/server/client";

export const dynamic = "force-dynamic";

export default async function NewRunPage() {
  const client = await getSpawndClient();
  const templates = await client.templates.list();

  return (
    <div className="flex flex-col gap-4 p-6">
      <Tabs defaultValue="plan">
        <TabsList>
          <TabsTrigger value="plan" className="font-mono text-xs">
            plan yaml
          </TabsTrigger>
          <TabsTrigger value="template" className="font-mono text-xs">
            from template
          </TabsTrigger>
        </TabsList>
        <TabsContent value="plan" className="pt-4">
          <PlanComposer />
        </TabsContent>
        <TabsContent value="template" className="pt-4">
          <TemplateRunner initialTemplates={templates} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
