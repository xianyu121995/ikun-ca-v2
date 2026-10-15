/** One active read and one coalesced follow-up; mutation callers wait for a subsequent read. */
export function coalescedRefresh(run: () => Promise<void>): () => Promise<void> {
    let active: Promise<void> | null = null;
    let queued: Promise<void> | null = null;
    function start() {
        const task: Promise<void> = Promise.resolve().then(run).finally(() => {
            if (active === task)
                active = null;
        });
        active = task;
        return task;
    }
    return () => {
        if (queued)
            return queued;
        if (!active)
            return start();
        queued = active.catch(() => { }).then(() => {
            queued = null;
            return start();
        });
        return queued;
    };
}
