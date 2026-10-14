import { closeStores, openStores, storesHealthy, type Store } from "@ikun/runtime";
const globals = globalThis as typeof globalThis & { ikunV2Stores?: Store[]; ikunV2Close?: boolean };
export function websiteReady(): boolean {
  if (!globals.ikunV2Stores) {
    const root = process.env.DATA_ROOT;
    if (!root) throw new Error("DATA_ROOT_REQUIRED");
    globals.ikunV2Stores = openStores("website", root);
  }
  if (!globals.ikunV2Close) {
    process.once("exit", () => closeStores(globals.ikunV2Stores ?? []));
    globals.ikunV2Close = true;
  }
  return storesHealthy(globals.ikunV2Stores);
}
