#!/usr/bin/env bash
# Fetch the upstream files that this repo cites, at pinned commits, and print
# the lines it relies on with their line numbers. Runs anywhere with curl.
# The full files go to .cache/src/ (not committed). Output: results/01-source-check.txt
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .cache/src results
C=.cache/src

# Ubuntu kernel 6.8.0-147.147 (the kernel on the test host), tag commit 0495f811
UK="https://git.launchpad.net/~ubuntu-kernel/ubuntu/+source/linux/+git/noble/plain"
UKID="0495f811cae0b8b7c718d936a2057b25cee7cf0c"
GH="https://raw.githubusercontent.com"
SYSTEMD="db11bab38ccf1ed257f310d29070843d4c58ea01"   # systemd v255
RUNC="29dd3dc2b13b4123162e5fe132504bb4b15569f1"      # runc v1.5.2 (the host's runc)
MOBY="70efc0e31da3a115fc87574d1b786fa2b867c346"      # moby docker-v29.9.3 (the host's Docker)
DOCS="c98501277b974550688eeed803c975e2665d6468"      # docker/docs main, 2026-11-05
K136="1b2171b110bb2a2542e1322035c6583ec86eb976"      # kubernetes v1.36.6
K137="c50e5395f1ae2d4a2c05f28fdcc38c0916cc1a32"      # kubernetes v1.37.2
ENH="92eb8a18eb831a21b610dd86053ecab7a663ec46"       # kubernetes/enhancements master, 2026-11-05

get() { [ -s "$C/$1" ] || curl -fsS -o "$C/$1" "$2"; }
get memcontrol.c        "$UK/mm/memcontrol.c?id=$UKID"
get memcontrol.h        "$UK/include/linux/memcontrol.h?id=$UKID"
get mm_internal.h       "$UK/mm/internal.h?id=$UKID"
get resume_user_mode.h  "$UK/include/linux/resume_user_mode.h?id=$UKID"
get cgroup-v2.rst       "$UK/Documentation/admin-guide/cgroup-v2.rst?id=$UKID"
get filemap.c           "$UK/mm/filemap.c?id=$UKID"
get systemd.resource-control.xml "$GH/systemd/systemd/$SYSTEMD/man/systemd.resource-control.xml"
get runc-fs2-memory.go  "$GH/opencontainers/runc/$RUNC/vendor/github.com/opencontainers/cgroups/fs2/memory.go"
get runc-systemd-v2.go  "$GH/opencontainers/runc/$RUNC/vendor/github.com/opencontainers/cgroups/systemd/v2.go"
get moby-daemon_unix.go "$GH/moby/moby/$MOBY/daemon/daemon_unix.go"
get docker-resource_constraints.md "$GH/docker/docs/$DOCS/content/manuals/engine/containers/resource_constraints.md"
for v in 136 137; do
  eval ref=\$K$v
  get "k$v-kube_features.go" "$GH/kubernetes/kubernetes/$ref/pkg/features/kube_features.go"
  get "k$v-kuberuntime_container_linux.go" "$GH/kubernetes/kubernetes/$ref/pkg/kubelet/kuberuntime/kuberuntime_container_linux.go"
  get "k$v-defaults.go" "$GH/kubernetes/kubernetes/$ref/pkg/kubelet/apis/config/v1beta1/defaults.go"
  get "k$v-types.go" "$GH/kubernetes/kubernetes/$ref/staging/src/k8s.io/kubelet/config/v1beta1/types.go"
done
get kep-2570.yaml  "$GH/kubernetes/enhancements/$ENH/keps/sig-node/2570-memory-qos/kep.yaml"
get kep-2570.md    "$GH/kubernetes/enhancements/$ENH/keps/sig-node/2570-memory-qos/README.md"

# print the lines of $1 from the first line matching $2 to the first later line matching $3
span() { awk -v a="$2" -v b="$3" 'f==0 && $0 ~ a {f=1} f==1 {printf "%5d  %s\n", NR, $0} f==1 && NR>s && $0 ~ b {exit} f==1 && s==0 {s=NR}' "$C/$1"; }
hit() { grep -n -E "$2" "$C/$1" | sed 's/^/  /' || echo "  (no line matches: $2)"; }
hdr() { printf '\n=== %s\n' "$*"; }

{
echo "# Upstream lines this repo relies on. Fetched $(date -u +%FT%TZ)."
hdr "Ubuntu kernel 6.8.0-147.147 mm/memcontrol.c ($UK/mm/memcontrol.c?id=$UKID)"
span memcontrol.c '^static unsigned long reclaim_high' '^}'
span memcontrol.c '^ \* Clamp the maximum sleep time per allocation batch' '^ #define MEMCG_DELAY_SCALING_SHIFT'
span memcontrol.c '^static u64 calculate_overage' '^}'
span memcontrol.c '^static unsigned long calculate_high_delay' '^}'
span memcontrol.c '^void mem_cgroup_handle_over_high' '^}'
span memcontrol.c '^static bool consume_stock' '^}'
span memcontrol.c '^static void __refill_stock' '^}'
span memcontrol.c '^static int try_charge_memcg' '^retry:'
span memcontrol.c '^done_restock:' '^}'
hdr "include/linux/memcontrol.h, mm/internal.h, include/linux/resume_user_mode.h (same tag)"
hit memcontrol.h 'define MEMCG_CHARGE_BATCH'
hit mm_internal.h 'define MAX_RECLAIM_RETRIES'
hit resume_user_mode.h 'mem_cgroup_handle_over_high'
hdr "mm/filemap.c (same tag): a page wait counts as a memory stall only for workingset folios"
span filemap.c '^static inline int folio_wait_bit_common' 'thrashing = true;'
hdr "Documentation/admin-guide/cgroup-v2.rst (same tag)"
span cgroup-v2.rst '^  memory.high$' '^  memory.max$'
span cgroup-v2.rst '^  memory.max$' '^  memory.reclaim$'
span cgroup-v2.rst '^	  high$' 'goes to OOM state'
hdr "systemd v255 man/systemd.resource-control.xml"
hit systemd.resource-control.xml 'This controls the <varname>memory\.(min|low|high|max)|Specify the (throttling|absolute) limit|use <varname>MemoryHigh=</varname> as the main|Memory usage may go|above the limit if unavoidable|aggressively in such cases|cannot be contained under the limit, out-of-memory killer|Specify the memory usage protection|be reclaimed to avoid invoking the OOM killer'
hdr "runc v1.5.2 vendor/github.com/opencontainers/cgroups/fs2/memory.go"
hit runc-fs2-memory.go '"memory\.(max|low|high|swap\.max)"|MemoryReservation'
hdr "runc v1.5.2 vendor/github.com/opencontainers/cgroups/systemd/v2.go"
hit runc-systemd-v2.go '"memory\.(high|low|max|swap\.max)": |newProp\("Memory(Max|Low|SwapMax|High)"|r\.MemoryReservation'
hdr "moby docker-v29.9.3 daemon/daemon_unix.go getMemoryResources"
span moby-daemon_unix.go '^func getMemoryResources' '^}'
hdr "docker/docs resource_constraints.md"
hit docker-resource_constraints.md '`--memory-reservation`|^\| `-m` or `--memory=`'
for v in 136 137; do
  hdr "kubernetes $( [ $v = 136 ] && echo v1.36.6 || echo v1.37.2 ) pkg/features/kube_features.go, kubelet config defaults and types"
  span "k$v-kube_features.go" '^	MemoryQoS: \{' '^	\},'
  hit "k$v-defaults.go" 'MemoryThrottlingFactor'
  span "k$v-types.go" 'MemoryThrottlingFactor specifies the factor' 'MemoryThrottlingFactor \*float64'
  hdr "kubernetes $( [ $v = 136 ] && echo v1.36.6 || echo v1.37.2 ) pkg/kubelet/kuberuntime/kuberuntime_container_linux.go (MemoryQoS)"
  span "k$v-kuberuntime_container_linux.go" '// Set memory.min and memory.high to enforce MemoryQoS' 'if len\(unified\) > 0'
done
hdr "KEP-2570 kep.yaml and README.md (kubernetes/enhancements $ENH)"
hit kep-2570.yaml '^(status|stage|latest-milestone):|^  (alpha|beta):'
hit kep-2570.md 'memoryThrottlingFactor` default changed|MemoryQoS` feature gate is enabled by default|v1.36 shipped as Alpha|it doesn.t progress further and stays stuck|kernel 5.9\+ \(October 2020\) resolved'
} > results/01-source-check.txt
wc -l results/01-source-check.txt
