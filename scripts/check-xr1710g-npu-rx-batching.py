#!/usr/bin/env python3
"""Check batch delivery before refill/NAPI completion using the actual poll body.

Pass a patched mt76 npu.c. This checks control flow with host stubs, not DMA,
mac80211 behavior, device recovery, or throughput.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

STUBS = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
typedef unsigned int u32;
enum mt76_rxq_id { RXQ };
struct sk_buff { int unused; };
struct airoha_npu { int unused; };
struct mt76_queue { int unused; };
struct mt76_dev;
struct napi_struct { struct mt76_dev *dev; };
struct driver {
    void (*rx_skb)(struct mt76_dev *, enum mt76_rxq_id, struct sk_buff *, u32 *);
    void (*rx_poll_complete)(struct mt76_dev *, enum mt76_rxq_id);
};
struct mt76_dev {
    struct napi_struct napi[1];
    struct mt76_queue q_rx[1];
    struct driver *drv;
    struct { struct airoha_npu *npu; } mmio;
};
static int available, queued, receives, flushes, fills, completions, irq_rearms;
static int locked, drop, complete_ok;
static struct sk_buff packet;
static void rcu_read_lock(void) { assert(!locked); locked = 1; }
static void rcu_read_unlock(void) { assert(locked); assert(!queued); locked = 0; }
#define rcu_dereference(p) (p)
#define mt76_priv(p) (p)
static struct sk_buff *mt76_npu_dequeue(struct mt76_dev *dev,
                                      struct mt76_queue *q, u32 *info)
{
    (void)dev; (void)q; assert(locked); *info = receives;
    if (!available) return NULL;
    available--; return &packet;
}
static void receive(struct mt76_dev *dev, enum mt76_rxq_id q,
                    struct sk_buff *skb, u32 *info)
{
    (void)dev; (void)q; assert(skb == &packet); assert(*info == (u32)receives);
    assert(!fills && !completions); receives++; if (!drop) queued++;
}
static void mt76_rx_poll_complete(struct mt76_dev *dev, enum mt76_rxq_id q,
                                 struct napi_struct *napi)
{
    (void)dev; (void)q; (void)napi; assert(locked);
    assert(!fills && !completions); flushes++; queued = 0;
}
static void mt76_npu_fill_rx_queue(struct mt76_dev *dev, struct mt76_queue *q)
{
    (void)dev; (void)q; assert(locked && !queued); fills++;
}
static bool napi_complete(struct napi_struct *napi)
{
    (void)napi; assert(locked && !queued); completions++; return complete_ok;
}
static void rearm(struct mt76_dev *dev, enum mt76_rxq_id q)
{
    (void)dev; (void)q; assert(completions && !queued); irq_rearms++;
}
'''
CASES = r'''
static void check(int frames, int budget, int active, int discard, int complete)
{
    struct driver drv = { receive, rearm };
    struct airoha_npu npu = {0};
    struct mt76_dev dev = { .drv = &drv, .mmio.npu = active ? &npu : NULL };
    int expected = active ? (frames < budget ? frames : budget) : 0;
    dev.napi[0].dev = &dev;
    available = frames; queued = receives = flushes = fills = 0;
    completions = irq_rearms = locked = 0; drop = discard; complete_ok = complete;
    assert(mt76_npu_rx_poll(&dev.napi[0], budget) == expected);
    assert(receives == expected && flushes == (expected > 0));
    assert(fills == active && !queued && !locked);
    assert(completions == (expected < budget));
    assert(irq_rearms == ((expected < budget) && complete));
}
int main(void)
{
    check(3, 64, 1, 0, 1); /* Early dequeue stop must still deliver the batch. */
    check(5, 2, 1, 0, 1);  /* Budget exhaustion delivers before repolling. */
    check(0, 64, 1, 0, 1);
    check(3, 0, 1, 0, 1);
    check(3, 64, 0, 0, 1);
    check(3, 64, 1, 1, 1); /* Callbacks can discard all frames. */
    check(3, 64, 1, 0, 0); /* Failed NAPI completion must not rearm IRQ. */
    return 0;
}
'''

source = Path(sys.argv[1]).read_text()
start = source.index("static int mt76_npu_rx_poll(")
end = source.index("\nstatic irqreturn_t mt76_npu_irq_handler", start)
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    program = root / "check.c"
    program.write_text(STUBS + source[start:end] + CASES)
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                    str(program), "-o", str(root / "check")], check=True)
    subprocess.run([str(root / "check")], check=True)
print("7 poll control-flow cases passed; device validation deferred")
