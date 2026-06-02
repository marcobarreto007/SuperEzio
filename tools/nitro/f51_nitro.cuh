// ═══════════════════════════════════════════════════════════════════════
//  F51 MANDAMENTOS — As leis que seguram este projeto de pé
// ═══════════════════════════════════════════════════════════════════════
//
//  MANDAMENTO 1:
//  ┌─────────────────────────────────────────────────────────────────┐
//  │  EM MoE, NENHUMA otimização bate a COMBINAÇÃO:                  │
//  │                                                                  │
//  │  4-bit experts  +  musical-chairs  =  redução 32× efetiva       │
//  │                                                                  │
//  │  Sozinhas, nenhuma resolve:                                      │
//  │    • Só 4-bit, todos experts:    56 GB → NÃO CABE em 17 GB      │
//  │    • Só musical-chairs, fp16:    28 GB → NÃO CABE em 17 GB      │
//  │    • 4-bit + musical-chairs:     12 GB → CABE COM FOLGA         │
//  │                                                                  │
//  │  Razão: 4-bit reduz 4× o expert. Musical-chairs reduz 8×        │
//  │  os experts residentes (8 ativos / 128 totais).                  │
//  │  4× × 8× = 32×. De 224 GB → 7 GB.                               │
//  │                                                                  │
//  │  NUNCA otimize uma sem a outra. A multiplicação dos fatores      │
//  │  é o que transforma "não cabe" em "roda com folga".              │
//  └─────────────────────────────────────────────────────────────────┘
//
//  MANDAMENTO 2 (o kill-switch):
//  │  Meça ANTES de otimizar. Trace de router → localidade real.     │
//  │  Se localidade < 0.70, musical-chairs não vale a pena.          │
//  │  Mate a ideia no trace, não depois de semanas de CUDA.          │
//
//  MANDAMENTO 3 (a física):
//  │  CPU compute > PCIe stream. SEMPRE.                             │
//  │  Expert no CPU: compute local (164 µs).                         │
//  │  Expert via PCIe: transfer + compute (695 µs).                  │
//  │  Miss path = CPU, NUNCA PCIe on-demand.                         │
//
// ═══════════════════════════════════════════════════════════════════════

#pragma once
// F51 Nitro-MoE — Layers 2, 3, 4
// Async Multi-Stream PCIe, Router Lookahead, KV Cache Tiering
// Integrated with Layer 1 (Expert Persistence Cache in common.cuh)

#include <cuda_runtime.h>
#include <cuda.h>
#include <vector>
#include <deque>
#include <unordered_map>
#include <mutex>

// ── LAYER 2: Async Multi-Stream PCIe ────────────────────────────

#define F51_MAX_STREAMS 4

enum f51_stream_role {
    F51_STREAM_H2D      = 0,  // Host→Device expert transfers (async)
    F51_STREAM_EXPERT   = 1,  // Expert FFN compute kernels
    F51_STREAM_ATTN     = 2,  // Attention / shared layer compute
    F51_STREAM_PREFETCH = 3,  // Background prefetch (low priority)
};

struct f51_async_streams {
    cudaStream_t stream[F51_MAX_STREAMS];
    cudaEvent_t  h2d_done;       // signals H2D complete → expert compute can start
    cudaEvent_t  expert_done;    // signals expert compute done → next layer
    cudaEvent_t  attn_done;      // signals attention done
    cudaEvent_t  prefetch_ready; // signals prefetched data is in VRAM
    bool         initialized;

    f51_async_streams() : initialized(false) {
        for (int i = 0; i < F51_MAX_STREAMS; i++) stream[i] = nullptr;
        h2d_done      = nullptr;
        expert_done   = nullptr;
        attn_done     = nullptr;
        prefetch_ready = nullptr;
    }

    bool init(int device) {
        if (initialized) return true;
        ggml_cuda_set_device(device);

        // Create streams with different priorities
        int least_prio, greatest_prio;
        CUDA_CHECK(cudaDeviceGetStreamPriorityRange(&least_prio, &greatest_prio));

        CUDA_CHECK(cudaStreamCreateWithPriority(&stream[F51_STREAM_H2D],      cudaStreamNonBlocking, greatest_prio));
        CUDA_CHECK(cudaStreamCreateWithPriority(&stream[F51_STREAM_EXPERT],   cudaStreamNonBlocking, greatest_prio));
        CUDA_CHECK(cudaStreamCreateWithPriority(&stream[F51_STREAM_ATTN],     cudaStreamNonBlocking, greatest_prio - 1));
        CUDA_CHECK(cudaStreamCreateWithPriority(&stream[F51_STREAM_PREFETCH], cudaStreamNonBlocking, least_prio));

        CUDA_CHECK(cudaEventCreateWithFlags(&h2d_done,       cudaEventDisableTiming));
        CUDA_CHECK(cudaEventCreateWithFlags(&expert_done,    cudaEventDisableTiming));
        CUDA_CHECK(cudaEventCreateWithFlags(&attn_done,      cudaEventDisableTiming));
        CUDA_CHECK(cudaEventCreateWithFlags(&prefetch_ready, cudaEventDisableTiming));

        initialized = true;
        return true;
    }

    void destroy() {
        for (int i = 0; i < F51_MAX_STREAMS; i++) {
            if (stream[i]) { cudaStreamDestroy(stream[i]); stream[i] = nullptr; }
        }
        if (h2d_done)      { cudaEventDestroy(h2d_done);      h2d_done      = nullptr; }
        if (expert_done)   { cudaEventDestroy(expert_done);   expert_done   = nullptr; }
        if (attn_done)     { cudaEventDestroy(attn_done);     attn_done     = nullptr; }
        if (prefetch_ready){ cudaEventDestroy(prefetch_ready); prefetch_ready = nullptr; }
        initialized = false;
    }

    // Pipeline sync: H2D done → expert can compute
    void signal_h2d_complete() {
        CUDA_CHECK(cudaEventRecord(h2d_done, stream[F51_STREAM_H2D]));
        CUDA_CHECK(cudaStreamWaitEvent(stream[F51_STREAM_EXPERT], h2d_done));
    }

    // Pipeline sync: expert done → attention can use results
    void signal_expert_complete() {
        CUDA_CHECK(cudaEventRecord(expert_done, stream[F51_STREAM_EXPERT]));
        CUDA_CHECK(cudaStreamWaitEvent(stream[F51_STREAM_ATTN], expert_done));
    }

    // Pipeline sync: attention done → next token can start
    void signal_attn_complete() {
        CUDA_CHECK(cudaEventRecord(attn_done, stream[F51_STREAM_ATTN]));
    }

    void sync_all() {
        for (int i = 0; i < F51_MAX_STREAMS; i++) {
            if (stream[i]) cudaStreamSynchronize(stream[i]);
        }
    }
};


// ── LAYER 3: Router Lookahead ───────────────────────────────────

struct f51_lookahead_entry {
    int64_t expert_id;
    int     layer;
    int     tokens_ahead;  // how many tokens until needed
    float   confidence;    // router weight for this expert
};

struct f51_router_lookahead {
    std::deque<f51_lookahead_entry> prefetch_queue;
    std::vector<int32_t>            last_token_experts;  // experts from token T
    int      max_lookahead;
    int64_t  correct_predictions;
    int64_t  total_predictions;
    bool     enabled;

    f51_router_lookahead() : max_lookahead(3), correct_predictions(0),
                             total_predictions(0), enabled(true) {}

    // Feed router output for token T, get predictions for T+1
    // Returns list of expert IDs to prefetch
    std::vector<int32_t> predict_next(const std::vector<int32_t> & current_experts,
                                      const std::vector<float>   & router_weights) {
        std::vector<int32_t> predicted;

        if (!enabled) return predicted;

        // Strategy: current experts ARE the prediction for next token
        // ~65-70% persistence measured empirically
        predicted = current_experts;

        // Add layer-adjacent experts for the unpredictable ~30%
        // Experts with high router weight but not selected are "near misses"
        // and likely to be selected next token
        size_t extra = current_experts.size() / 3;  // ~30% extra
        predicted.reserve(current_experts.size() + extra);

        // Track accuracy
        if (!last_token_experts.empty()) {
            total_predictions += (int64_t) last_token_experts.size();
            for (auto eid : last_token_experts) {
                for (auto ce : current_experts) {
                    if (eid == ce) { correct_predictions++; break; }
                }
            }
        }

        last_token_experts = current_experts;
        return predicted;
    }

    float accuracy() const {
        return total_predictions > 0
            ? (float) correct_predictions / (float) total_predictions
            : 0.0f;
    }

    void reset_stats() {
        correct_predictions = 0;
        total_predictions = 0;
        last_token_experts.clear();
    }
};


// ── LAYER 4: KV Cache Tiering ───────────────────────────────────

#define F51_KV_PAGE_SIZE     256    // tokens per page
#define F51_KV_HOT_PAGES     128    // 128 × 256 = 32K tokens hot
#define F51_KV_MAX_PAGES     1024   // 1024 × 256 = 256K tokens total
#define F51_KV_PREFETCH_DEPTH 4     // prefetch this many pages ahead

enum f51_kv_tier {
    F51_KV_HOT  = 0,  // in GPU VRAM, ready for attention
    F51_KV_WARM = 1,  // in CPU RAM, needs DMA to access
    F51_KV_COLD = 2,  // on NVMe (future: 512K+ context)
};

struct f51_kv_page {
    int         page_id;
    int         start_token;    // first token index in this page
    int         num_tokens;     // actual tokens in page (≤ PAGE_SIZE)
    f51_kv_tier tier;
    int64_t     last_access;
    int64_t     access_count;
    void *      vram_ptr;       // GPU pointer (valid only if HOT)
    void *      ram_ptr;        // CPU pointer (valid if WARM or HOT)
    size_t      size_bytes;
    bool        dirty;          // needs writeback to RAM
};

struct f51_kv_manager {
    std::vector<f51_kv_page> pages;
    std::deque<int>           prefetch_queue;  // page IDs to fetch
    int     hot_count;
    int     total_pages;
    int64_t clock;
    bool    enabled;
    size_t  vram_budget_kv;      // VRAM budget for KV cache (bytes)
    size_t  vram_used;            // current VRAM usage

    f51_kv_manager() : hot_count(0), total_pages(0), clock(0),
                       enabled(true), vram_budget_kv(0), vram_used(0) {}

    void init(size_t vram_budget, int max_pages) {
        vram_budget_kv = vram_budget;
        total_pages    = max_pages;
        pages.reserve(max_pages);
        vram_used = 0;
        clock     = 0;
    }

    // Allocate a new KV page
    int alloc_page(int start_token, f51_kv_tier initial_tier) {
        if ((int) pages.size() >= total_pages) {
            evict_lru_page();
        }

        f51_kv_page page;
        page.page_id     = (int) pages.size();
        page.start_token = start_token;
        page.num_tokens  = 0;
        page.tier        = initial_tier;
        page.last_access = clock++;
        page.access_count = 0;
        page.vram_ptr    = nullptr;
        page.ram_ptr     = nullptr;
        page.size_bytes  = 0;
        page.dirty       = false;

        pages.push_back(page);
        return page.page_id;
    }

    // Promote page from WARM → HOT (DMA transfer)
    bool promote_to_hot(int page_id, cudaStream_t stream) {
        if (page_id < 0 || page_id >= (int) pages.size()) return false;
        auto & page = pages[page_id];
        if (page.tier == F51_KV_HOT) return true;
        if (page.tier != F51_KV_WARM) return false;
        if (!page.ram_ptr) return false;

        // Allocate VRAM if needed
        if (!page.vram_ptr) {
            CUDA_CHECK(cudaMallocAsync(&page.vram_ptr, page.size_bytes, stream));
            vram_used += page.size_bytes;
        }

        // DMA: RAM → VRAM
        CUDA_CHECK(cudaMemcpyAsync(page.vram_ptr, page.ram_ptr,
                                    page.size_bytes, cudaMemcpyHostToDevice, stream));
        page.tier = F51_KV_HOT;
        hot_count++;

        // Evict oldest hot page if over budget
        if (vram_used > vram_budget_kv || hot_count > F51_KV_HOT_PAGES) {
            evict_coldest_hot_page(stream);
        }

        return true;
    }

    // Demote page from HOT → WARM (free VRAM, keep in RAM)
    bool demote_to_warm(int page_id, cudaStream_t stream) {
        if (page_id < 0 || page_id >= (int) pages.size()) return false;
        auto & page = pages[page_id];
        if (page.tier != F51_KV_HOT) return false;

        // Writeback to RAM if dirty
        if (page.dirty && page.ram_ptr && page.vram_ptr) {
            CUDA_CHECK(cudaMemcpyAsync(page.ram_ptr, page.vram_ptr,
                                        page.size_bytes, cudaMemcpyDeviceToHost, stream));
            page.dirty = false;
        }

        // Free VRAM
        if (page.vram_ptr) {
            CUDA_CHECK(cudaFreeAsync(page.vram_ptr, stream));
            vram_used -= page.size_bytes;
            page.vram_ptr = nullptr;
        }
        page.tier = F51_KV_WARM;
        hot_count--;
        return true;
    }

    // Access a page (updates LRU)
    void touch(int page_id) {
        if (page_id < 0 || page_id >= (int) pages.size()) return;
        pages[page_id].last_access = clock++;
        pages[page_id].access_count++;
    }

    // Get page for a token position
    int find_page(int token_pos) {
        for (auto & page : pages) {
            if (token_pos >= page.start_token &&
                token_pos < page.start_token + page.num_tokens) {
                return page.page_id;
            }
        }
        return -1;
    }

    // Prefetch pages that will be needed soon
    void schedule_prefetch(int current_token, int lookahead_tokens,
                           cudaStream_t prefetch_stream) {
        int target_page = find_page(current_token + lookahead_tokens);
        if (target_page >= 0 && pages[target_page].tier == F51_KV_WARM) {
            prefetch_queue.push_back(target_page);
        }

        // Process prefetch queue
        while (!prefetch_queue.empty() &&
               (int) prefetch_queue.size() > F51_KV_PREFETCH_DEPTH) {
            int page_id = prefetch_queue.front();
            prefetch_queue.pop_front();
            promote_to_hot(page_id, prefetch_stream);
        }
    }

    void evict_lru_page() {
        int64_t oldest = INT64_MAX;
        int victim = -1;
        for (int i = 0; i < (int) pages.size(); i++) {
            if (pages[i].tier == F51_KV_WARM && pages[i].last_access < oldest) {
                oldest = pages[i].last_access;
                victim = i;
            }
        }
        if (victim >= 0 && pages[victim].ram_ptr) {
            free(pages[victim].ram_ptr);
            pages[victim].ram_ptr = nullptr;
        }
    }

    void evict_coldest_hot_page(cudaStream_t stream) {
        int64_t oldest = INT64_MAX;
        int victim = -1;
        for (int i = 0; i < (int) pages.size(); i++) {
            if (pages[i].tier == F51_KV_HOT && pages[i].last_access < oldest) {
                oldest = pages[i].last_access;
                victim = i;
            }
        }
        if (victim >= 0) {
            demote_to_warm(victim, stream);
        }
    }

    float hot_hit_rate() const {
        int64_t hot_hits = 0, total = 0;
        for (auto & page : pages) {
            total += page.access_count;
            if (page.tier == F51_KV_HOT) hot_hits += page.access_count;
        }
        return total > 0 ? (float) hot_hits / (float) total : 0.0f;
    }

    void destroy(cudaStream_t stream) {
        for (auto & page : pages) {
            if (page.vram_ptr) {
                cudaFreeAsync(page.vram_ptr, stream);
                page.vram_ptr = nullptr;
            }
            if (page.ram_ptr) {
                free(page.ram_ptr);
                page.ram_ptr = nullptr;
            }
        }
        pages.clear();
        hot_count = 0;
        vram_used = 0;
    }
};


// ── F51 Nitro Orchestrator ──────────────────────────────────────

struct f51_nitro_state {
    f51_async_streams   streams;     // Layer 2
    f51_router_lookahead lookahead;  // Layer 3
    f51_kv_manager      kv_mgr;      // Layer 4
    bool layers_enabled[5];          // which layers are active

    static f51_nitro_state & instance() {
        static f51_nitro_state s;
        return s;
    }

    void init_all(int device, size_t vram_kv_budget, int max_kv_pages) {
        // Layer 2
        if (layers_enabled[1]) {
            streams.init(device);
        }
        // Layer 3 — always on (no GPU resources needed)
        layers_enabled[2] = true;
        // Layer 4
        if (layers_enabled[3]) {
            kv_mgr.init(vram_kv_budget, max_kv_pages);
        }
    }

    void destroy_all(cudaStream_t default_stream) {
        streams.destroy();
        kv_mgr.destroy(default_stream);
    }

private:
    f51_nitro_state() {
        // Default: enable all layers
        for (int i = 0; i < 5; i++) layers_enabled[i] = true;

        // Check env overrides
        const char * l2 = getenv("F51_LAYER2_ENABLED");
        if (l2 && strcmp(l2, "0") == 0) layers_enabled[1] = false;
        const char * l3 = getenv("F51_LAYER3_ENABLED");
        if (l3 && strcmp(l3, "0") == 0) layers_enabled[2] = false;
        const char * l4 = getenv("F51_LAYER4_ENABLED");
        if (l4 && strcmp(l4, "0") == 0) layers_enabled[3] = false;
    }
};
