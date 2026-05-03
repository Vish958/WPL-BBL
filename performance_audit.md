# Performance Audit — `powerplay_drs_metrics.py`

> **Dataset**: 496K rows × 40 cols | **Raw**: 503 MB | **With categories**: 41 MB  
> **Runtime**: Streamlit Cloud (limited to ~1 GB RAM)

---

## Critical Issues (Fix These First)

### 1. `st.cache_data.clear()` on Every Rerun — **SEVERITY: CRITICAL**

**Line 22** — This single line **destroys all caching on every page load**.

```python
# Force clear cache on startup to ensure new player matching logic is used
# Remove this after confirming the fix works
st.cache_data.clear()  # ← KILLS load_data cache, forces re-read of parquet EVERY time
```

**Impact**: The 41 MB parquet is re-read and re-processed on **every** sidebar click, filter change, or widget interaction. This alone can cause 200-400ms+ delays per rerun and doubles peak memory because old + new DataFrames coexist momentarily.

**Fix**: Remove line 22. The `_cache_version` parameter already handles cache invalidation.

---

### 2. Triple Full-DataFrame Copy on Every Rerun — **SEVERITY: HIGH**

Lines 321, 333, and per-metric copies (1673, 2282, 2503, 2811, 2993, 5060, 5217, etc.)

```python
fdf = df.copy()              # 41 MB copy #1
fdf_no_team = fdf.copy()     # 41 MB copy #2
# Then inside each metric:
bowling_df = df.copy()        # 41 MB copy #3 (line 1673)
edc_df = df.copy()            # 41 MB copy #4 (line 5217)
oes_df = df.copy()            # 41 MB copy #5 (line 2993)
```

**Impact**: At peak, 3-5 full copies exist simultaneously = **120-200 MB** of redundant data. On 1 GB Streamlit Cloud, this is 12-20% of total RAM just for copies.

**Fix**: Use filtered views instead of copies. Only `.copy()` when you actually mutate the DataFrame. For read-only filtering (`.isin()`, boolean masks), views are safe and free.

```python
# BEFORE (120 MB wasted)
fdf = df.copy()
fdf_no_team = fdf.copy()

# AFTER (0 MB wasted)
fdf = df  # start with the cached original
if selected_leagues:
    fdf = fdf[fdf['league'].isin(selected_leagues)]
if selected_years:
    fdf = fdf[fdf['year'].isin(selected_years)]
# .copy() only for match_number because we ADD a column
fdf = fdf.copy()
fdf['match_number'] = ...
fdf_no_team = fdf  # just a reference, no mutation needed before team filter
```

---

### 3. `venue_map` Lambda Mapping on Full DataFrame — **SEVERITY: HIGH**

Lines 303-304 — runs on **every rerun** (not cached), and uses slow `.map(lambda)`:

```python
df['venue'] = df['match_id'].astype(str).map(lambda x: venue_map.get(x, {}).get('venue', 'Unknown'))
df['city'] = df['match_id'].astype(str).map(lambda x: venue_map.get(x, {}).get('city', 'Unknown'))
```

**Impact**: 496K lambda calls × 2 = ~1M function calls per rerun. Also **mutates the cached `df`** which can cause cache corruption.

**Fix**: Pre-build lookup Series and use vectorized `.map()`, and do this inside `load_data()`:

```python
# Inside load_data():
venue_s = pd.Series({k: v['venue'] for k, v in venue_map.items()})
city_s = pd.Series({k: v['city'] for k, v in venue_map.items()})
df['venue'] = df['match_id'].astype(str).map(venue_s).fillna('Unknown')
df['city'] = df['match_id'].astype(str).map(city_s).fillna('Unknown')
```

---

### 4. Row-level `.apply(lambda)` for Opponent Team — **SEVERITY: MEDIUM-HIGH**

Lines 425, 466, and throughout the code:

```python
pp['bowling_team'] = pp.apply(lambda row: get_opponent_team(row['teams'], str(row['team'])), axis=1)
stats['Opponent'] = stats.apply(get_opponent, axis=1)
```

**Impact**: `apply(axis=1)` is Python-speed iteration disguised as pandas. For powerplay data (~150K rows), this is 150K Python function calls.

**Fix**: Vectorize with string operations:

```python
# Vectorized opponent extraction
teams_split = pp['teams'].astype(str).str.replace(' vs ', ' v ').str.split(' v ', n=1)
team_str = pp['team'].astype(str)
team_a = teams_split.str[0].str.strip()
team_b = teams_split.str[1].str.strip()
pp['bowling_team'] = np.where(team_a == team_str, team_b, team_a)
```

---

## Medium Issues

### 5. Python `for` Loop Groupby Iterations — **SEVERITY: MEDIUM**

Lines 761, 829, 891, 967, 1025, 1315, 3588, 3833 — Pattern:

```python
for (match_id, innings, batter, team), grp in ipl.groupby([...]):
    grp = grp.sort_values('ball_float')
    cumruns = grp['runs.batter'].cumsum()
    ...
    results.append({...})
return pd.DataFrame(results)
```

**Impact**: `fastest_individual_milestones` iterates over ~15K groups (unique batter × match × innings). Each group creates a sub-DataFrame. This is the **slowest pattern in pandas**.

**Fix (selective)**: The critical ones (`innings_progression` line 3588 and `compute_batting_positions_bo` line 3833) should be vectorized. The milestone functions are harder to vectorize but should be wrapped in `@st.cache_data`:

```python
@st.cache_data(show_spinner="Computing milestones...")
def fastest_individual_milestones(df_hash, df_):
    ...  # existing code
```

### 6. No Caching on Heavy Computation Functions — **SEVERITY: MEDIUM**

These functions are called on every rerun but are **not cached**:
- `powerplay_score_tracker()` — groupby on 150K+ rows
- `extra_deliveries_cost()` — shift + groupby on full dataset
- `boundary_less_overs_spell()` — for-loop groupby
- `fastest_individual_milestones()` — for-loop groupby
- `fastest_team_milestones()` — for-loop groupby
- `bowler_first_spell_wickets()` — for-loop groupby
- `yearwise_batter_sr_comparison()` — multiple groupby + merge
- `yearwise_bowler_comparison()` — multiple groupby + merge

**Fix**: Wrap with `@st.cache_data`. Use a hash of the input DataFrame's shape + filters as cache key:

```python
@st.cache_data(show_spinner="Loading powerplay stats...")
def powerplay_score_tracker(_df_hash, df_, mode='batting', filter_teams=None):
    ...
```

### 7. Redundant `.astype(str)` on Category Columns — **SEVERITY: LOW-MEDIUM**

Throughout the code, category columns are repeatedly cast to string:

```python
lr_df['batter'].apply(lambda x: get_player_batting_hand(x, player_data_cache))  # line 3129
ps_df['bowler'].apply(lambda x: get_player_bowling_type(x, player_data_cache))   # line 3262
```

**Impact**: `.apply()` on 150K+ rows with string conversion + dictionary lookup = slow.

**Fix**: Build mapping once, then use vectorized `.map()`:

```python
# Build mapping Series once
bowling_type_map = {k: v['bowling_type'] for k, v in player_data_cache.items() if k != '_errors'}
ps_df['bowling_type'] = ps_df['bowler'].astype(str).str.lower().map(bowling_type_map).fillna('Unknown')
```

---

## Low Priority (Nice-to-Have)

### 8. `load_data()` Missing Int16 Downcast

The `load_data()` function converts to category but **doesn't downcast integers**, even though the previous session showed that int16 downcast reduces memory from 92 MB → 41 MB.

**Fix**: Add integer downcasting inside `load_data()`.

---

## Recommended Implementation Order

| Priority | Fix | Memory Saved | Time Saved | Risk |
|----------|-----|-------------|------------|------|
| 1 | Remove `st.cache_data.clear()` | ~41 MB | 200-400ms/rerun | Zero |
| 2 | Eliminate redundant `.copy()` | ~80-120 MB | 50-100ms/rerun | Low |
| 3 | Vectorize venue mapping | ~0 MB | 100-200ms/rerun | Low |
| 4 | Vectorize opponent extraction | ~0 MB | 50-100ms/rerun | Low |
| 5 | Cache heavy functions | ~0 MB | 500ms-2s/rerun | Low |
| 6 | Add int16 downcast | ~50 MB | 0 | Low |
| 7 | Vectorize player lookups | ~0 MB | 100-300ms | Low |
| 8 | Refactor for-loop groupbys | ~0 MB | Variable | Medium |

> [!IMPORTANT]
> Fixes 1-4 alone should eliminate the crash. Fix 1 is the single biggest win — it makes caching actually work.
