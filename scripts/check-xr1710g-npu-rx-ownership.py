#!/usr/bin/env python3
"""Exercise the real dequeue function with simulated DMA buffer ownership.

Usage: check-mt76-npu-rx.py /path/to/mt76 [--unpatched]
The unpatched run must fail the partial-descriptor regression. This host test
cannot validate device DMA ordering or prove the cause of a hardware crash.
"""
from pathlib import Path
import argparse
import subprocess
import tempfile
import re

PATCH = Path(__file__).resolve().parents[1] / "package/kernel/mt76/patches/9997-wifi-mt76-npu-preserve-rx-ring-ownership.patch"
STUBS = r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
typedef uint32_t u32;
#define NPU_RX_DMA_PKT_COUNT_MASK 0xe0000000U
#define NPU_RX_DMA_DESC_CUR_LEN_MASK 0x7ffeU
#define NPU_RX_DMA_DESC_DONE_MASK 1U
#define FIELD_GET(mask, v) (((v) & (mask)) >> __builtin_ctz(mask))
#define max_t(t, a, b) ((t)(a) > (t)(b) ? (t)(a) : (t)(b))
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define READ_ONCE(x) (*(volatile __typeof__(x) *)&(x))
#define dma_rmb() ((void)0)
#define Q_WRITE(q, reg, val) ((q)->published = (val))
struct page { int recycled; };
struct skb_shared_info { int nr_frags; struct page *frags[17]; };
struct sk_buff { struct page *head; int len; bool recycle; struct skb_shared_info info; };
struct airoha_npu_rx_dma_desc { u32 ctrl, info; };
struct mt76_queue_entry { void *buf; uintptr_t dma_addr[1]; int dma_len[1]; };
struct mt76_queue { void *desc; struct mt76_queue_entry *entry; int tail, queued, ndesc, buf_size, published; void *page_pool; };
struct mt76_dev { void *dma_dev; };
static int allocations, releases, fail_alloc, syncs, reused;
static struct page *virt_to_head_page(void *p) { return p; }
static void *page_address(struct page *p) { return p; }
#define page_pool_get_dma_dir(p) 0
#define dma_sync_single_for_cpu(dev, addr, len, dir) (++syncs)
static struct sk_buff *napi_build_skb(void *buf, int size) {
    (void)size;
    if (fail_alloc) return NULL;
    if (((struct page *)buf)->recycled) reused++;
    struct sk_buff *skb = calloc(1, sizeof(*skb));
    if (!skb) abort();
    allocations++; skb->head = buf; return skb;
}
static void __skb_put(struct sk_buff *skb, int len) { skb->len += len; }
static void skb_reset_mac_header(struct sk_buff *skb) { (void)skb; }
static void skb_mark_for_recycle(struct sk_buff *skb) { skb->recycle = true; }
static struct skb_shared_info *skb_shinfo(struct sk_buff *skb) { return &skb->info; }
static void skb_add_rx_frag(struct sk_buff *skb, int n, struct page *page, int offset, int len, int size) {
    (void)offset; (void)size;
    if (page->recycled) reused++;
    skb->info.frags[n] = page; skb->info.nr_frags++; skb->len += len;
}
static void dev_kfree_skb(struct sk_buff *skb) {
    if (!skb) return;
    if (skb->recycle) {
        skb->head->recycled++; releases++;
        for (int i = 0; i < skb->info.nr_frags; i++) {
            skb->info.frags[i]->recycled++; releases++;
        }
    }
    free(skb);
}
'''
CASES = r'''
#define CHECK(c, why) do { if (!(c)) { fprintf(stderr, "%s\n", why); return 1; } } while (0)
static struct page pages[4];
static struct airoha_npu_rx_dma_desc desc[4];
static struct mt76_queue_entry entries[4];
static struct mt76_queue queue;
static struct mt76_dev device;
static void setup(int tail, int queued, int count) {
    memset(pages, 0, sizeof(pages)); memset(desc, 0, sizeof(desc));
    allocations = releases = fail_alloc = syncs = reused = 0;
    for (int i = 0; i < 4; i++) {
        entries[i].buf = &pages[i]; entries[i].dma_len[0] = 1800;
        desc[i].ctrl = (100 << 1) | 1;
    }
    desc[tail].info = (u32)count << 29;
    queue = (struct mt76_queue){ .desc=desc, .entry=entries, .tail=tail,
        .queued=queued, .ndesc=4, .buf_size=2048, .published=-1 };
}
int main(void) {
    u32 info = 0; struct sk_buff *skb;
    /* An incomplete wrapped packet must leave every page ring-owned. */
    setup(3, 4, 2); desc[0].ctrl &= ~1U;
    skb = mt76_npu_dequeue(&device, &queue, &info);
    CHECK(!skb, "incomplete packet was returned");
    CHECK(!allocations && !releases && !syncs,
          "REGRESSION: incomplete packet transferred/recycled a ring-owned buffer");
    CHECK(queue.tail == 3 && queue.queued == 4 && queue.published == -1,
          "incomplete chain changed consumer state");
    desc[0].ctrl |= 1;
    skb = mt76_npu_dequeue(&device, &queue, &info);
    CHECK(skb && skb->len == 200 && !reused, "retry reused recycled data");
    CHECK(queue.tail == 1 && queue.queued == 2 && queue.published == 1,
          "complete wrapped packet was not consumed exactly once");
    dev_kfree_skb(skb);
    CHECK(releases == 2 && pages[3].recycled == 1 && pages[0].recycled == 1,
          "completed packet did not release each page exactly once");
    setup(0, 4, 2); fail_alloc = 1;
    CHECK(!mt76_npu_dequeue(&device, &queue, &info), "allocation failure returned an skb");
    CHECK(!releases && queue.tail == 0 && queue.queued == 4,
          "allocation failure lost ring ownership");
    fail_alloc = 0; skb = mt76_npu_dequeue(&device, &queue, &info);
    CHECK(skb && !reused, "retry after allocation failure failed"); dev_kfree_skb(skb);
    setup(0, 0, 1);
    CHECK(!mt76_npu_dequeue(&device, &queue, &info) && !allocations,
          "empty ring consumed stale descriptor");
    setup(0, 1, 2);
    CHECK(!mt76_npu_dequeue(&device, &queue, &info) && !allocations,
          "packet exceeded ring-owned descriptors");
    setup(0, 4, 2); desc[0].ctrl &= ~1U;
    CHECK(!mt76_npu_dequeue(&device, &queue, &info) && !syncs,
          "device-owned first descriptor was consumed");
    setup(0, 4, 0); skb = mt76_npu_dequeue(&device, &queue, &info);
    CHECK(skb && skb->len == 100 && queue.tail == 1 && queue.queued == 3,
          "zero-count single-buffer convention changed"); dev_kfree_skb(skb);
    puts("PASS: partial chain, wraparound retry, allocation failure, empty ring, count bounds, ownership, single buffer");
    return 0;
}
'''

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--kernel-header", type=Path, required=True)
    parser.add_argument("--unpatched", action="store_true")
    parser.add_argument("--prepared", action="store_true", help="source already contains the ownership fix")
    args = parser.parse_args()
    match = re.search(r"#define\s+NPU_RX_DMA_PKT_COUNT_MASK\s+GENMASK\((\d+),\s*(\d+)\)", args.kernel_header.read_text())
    if not match:
        parser.error("unsupported or missing packet count definition in actual kernel header")
    high, low = map(int, match.groups())
    if not 0 <= low < high < 32:
        parser.error("packet count must have at least two bits within a 32-bit descriptor")
    mask = ((1 << (high - low + 1)) - 1) << low
    stubs = STUBS.replace("0xe0000000U", hex(mask) + "U")
    cases = CASES.replace("(u32)count << 29", "(u32)count << %d" % low)
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "npu.c"
        source.write_text((args.source / "npu.c").read_text())
        if not args.unpatched and not args.prepared:
            subprocess.run(["patch", "-s", "-p1", "-i", str(PATCH)], cwd=root, check=True)
        text = source.read_text()
        function = text[text.index("static struct sk_buff *mt76_npu_dequeue("):text.index("\nvoid mt76_npu_check_ppe(")]
        harness = root / "test.c"
        harness.write_text(stubs + function + cases)
        binary = root / "test"
        subprocess.run(["cc", "-std=gnu11", "-Wall", "-Wextra", "-Wno-unused-parameter", "-Wno-sign-compare", str(harness), "-o", str(binary)], check=True)
        return subprocess.run([str(binary)]).returncode

if __name__ == "__main__":
    raise SystemExit(main())
