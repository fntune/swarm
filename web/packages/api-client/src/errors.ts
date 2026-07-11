export interface ValidationErrorItem {
  loc: (string | number)[];
  msg: string;
  type: string;
}

function isValidationErrorItem(value: unknown): value is ValidationErrorItem {
  return (
    typeof value === "object" &&
    value !== null &&
    Array.isArray((value as ValidationErrorItem).loc) &&
    typeof (value as ValidationErrorItem).msg === "string"
  );
}

export class SpawndApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, body: unknown, message?: string) {
    super(message ?? `spawnd API request failed with status ${status}`);
    this.name = "SpawndApiError";
    this.status = status;
    this.body = body;
  }

  /** The FastAPI `detail` payload, whatever shape it has. */
  get detail(): unknown {
    if (typeof this.body === "object" && this.body !== null && "detail" in this.body) {
      return (this.body as { detail: unknown }).detail;
    }
    return undefined;
  }

  /**
   * Human-readable validation messages. spawnd plan validation returns
   * `detail: string[]`; pydantic body validation returns
   * `detail: ValidationErrorItem[]`; both flatten here.
   */
  get validationMessages(): string[] {
    const detail = this.detail;
    if (typeof detail === "string") return [detail];
    if (!Array.isArray(detail)) return [];
    return detail.map((item) => {
      if (typeof item === "string") return item;
      if (isValidationErrorItem(item)) {
        const location = item.loc.filter((part) => part !== "body").join(".");
        return location ? `${location}: ${item.msg}` : item.msg;
      }
      return JSON.stringify(item);
    });
  }

  static async fromResponse(response: Response): Promise<SpawndApiError> {
    let body: unknown = null;
    const text = await response.text().catch(() => "");
    if (text) {
      try {
        body = JSON.parse(text);
      } catch {
        body = text;
      }
    }
    const error = new SpawndApiError(response.status, body);
    const messages = error.validationMessages;
    if (messages.length > 0) {
      error.message = messages.join("; ");
    }
    return error;
  }
}
