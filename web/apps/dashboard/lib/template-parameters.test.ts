import { describe, expect, it } from "vitest";

import { initialParameterValues, templateParameters } from "./template-parameters";

describe("template parameters", () => {
  it("extracts placeholders across every template field", () => {
    expect(
      templateParameters({
        id: "tpl-1",
        name: "template",
        description: null,
        plan_template: "name: {name}\nrepo: {repo}",
        source_repo_template: "https://github.com/{repo}.git",
        source_ref_template: "refs/heads/{branch}",
        created_at: "2026-07-11T00:00:00Z",
        updated_at: "2026-07-11T00:00:00Z",
      }),
    ).toEqual(["branch", "name", "repo"]);
  });

  it("initializes every rendered field before submission", () => {
    expect(initialParameterValues(["branch", "repo"])).toEqual({ branch: "", repo: "" });
  });
});
