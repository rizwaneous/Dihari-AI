import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { describe, expect, it, vi } from "vitest";

const dir = path.resolve(__dirname, "../../../locales");
const load = (l: string) => JSON.parse(readFileSync(path.join(dir, `${l}.json`), "utf-8"));

describe("locales", () => {
  it("ur and en define the same keys", () => {
    expect(Object.keys(load("ur")).sort()).toEqual(Object.keys(load("en")).sort());
  });
  it("every t('...') key used in the UI exists in the locale files", () => {
    const src = path.resolve(__dirname, "..");
    const files = [...readdirSync(src), ...readdirSync(path.join(src, "pages")).map((f) => `pages/${f}`), ...readdirSync(path.join(src, "components")).map((f) => `components/${f}`)].filter((f) => f.endsWith(".tsx"));
    const keys = new Set<string>();
    for (const f of files) for (const m of readFileSync(path.join(src, f), "utf-8").matchAll(/\bt\("([A-Za-z_.]+)"/g)) if (!m[1].endsWith(".")) keys.add(m[1]);
    const ur = load("ur");
    const missing = [...keys].filter((k) => !(k in ur));
    expect(missing).toEqual([]);
  });
  it("Urdu is RTL", () => expect(load("ur")._meta.dir).toBe("rtl"));
});

describe("api retry", () => {
  it("retries network failures on GET then succeeds", async () => {
    let n = 0;
    vi.stubGlobal("fetch", async () => { if (++n < 3) throw new TypeError("net"); return new Response(JSON.stringify({ ok: 1 }), { headers: { "content-type": "application/json" } }); });
    vi.stubGlobal("localStorage", { getItem: () => "", setItem() {}, removeItem() {} });
    const { api } = await import("../api");
    expect(await api("/x")).toEqual({ ok: 1 });
    expect(n).toBe(3);
  });
  it("surfaces ApiError code without retrying 4xx", async () => {
    let n = 0;
    vi.stubGlobal("fetch", async () => { n++; return new Response(JSON.stringify({ detail: "otp_wrong" }), { status: 400, headers: { "content-type": "application/json" } }); });
    const { api } = await import("../api");
    await expect(api("/y", { method: "POST", body: {} })).rejects.toMatchObject({ status: 400, code: "otp_wrong" });
    expect(n).toBe(1);
  });
});
