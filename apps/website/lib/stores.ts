import { closeStores, inspectStores, storesHealthy, probeProjectsIpc } from "@ikun/runtime";
export async function websiteReady(): Promise<boolean> {
  const root = process.env.DATA_ROOT;
  if (!root) throw new Error("DATA_ROOT_REQUIRED");
  const socketPath = process.env.IKUN_PROJECTS_IPC_SOCKET;
  const token = process.env.IKUN_PROJECTS_IPC_TOKEN;
  const buildSha = process.env.IKUN_PROJECTS_BUILD_SHA;
  const ipc = Boolean(socketPath || token || buildSha);
  if (ipc && (!socketPath || !token || !buildSha)) return false;
  const stores = inspectStores("website", root, ipc ? { names: ["auth"] } : {});
  try {
    return storesHealthy(stores) && (!ipc || await probeProjectsIpc({ socketPath: socketPath!, token: token!, buildSha: buildSha! }));
  } finally { closeStores(stores); }
}
