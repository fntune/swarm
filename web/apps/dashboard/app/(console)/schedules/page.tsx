import { ScheduleManager } from "@/components/schedules/schedule-manager";
import { getSpawndClient } from "@/lib/server/client";

export const dynamic = "force-dynamic";

export default async function SchedulesPage() {
  const client = await getSpawndClient();
  const [schedules, templates] = await Promise.all([
    client.schedules.list(),
    client.templates.list(),
  ]);

  return (
    <div className="p-6">
      <ScheduleManager initialSchedules={schedules} initialTemplates={templates} />
    </div>
  );
}
