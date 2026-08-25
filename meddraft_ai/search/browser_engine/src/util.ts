export async function jitterDelay(minMs: number, maxMs: number): Promise<void> {
  const ms = Math.floor(Math.random() * (maxMs - minMs + 1)) + minMs;
  await new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Races a promise against a deadline. The timer is unref'd so a settled
 * operation never keeps the process alive just because the deadline is pending.
 */
export function withTimeout<T>(promise: Promise<T>, ms: number, label: string): Promise<T> {
  let cancel: () => void = () => {};
  const timeout = new Promise<never>((_, reject) => {
    const handle = setTimeout(() => reject(new Error(`Operation timed out after ${ms}ms: ${label}`)), ms);
    handle.unref();
    cancel = () => clearTimeout(handle);
  });
  return Promise.race([promise, timeout]).finally(cancel) as Promise<T>;
}
