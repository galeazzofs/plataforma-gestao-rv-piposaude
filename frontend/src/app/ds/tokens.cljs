(ns app.ds.tokens)

;; ============================================
;; Pipo Saúde — design tokens
;; ----------------------------------------------
;; Names are kept stable so existing inline styles
;; across views pick up the new values without churn.
;; Reference: handoff bundle "Plataforma RV / Todas as Telas".
;; ============================================

;; Brand
(def color-primary "#000000")
(def color-white   "#FFFFFF")
(def color-night   "#060D41")
(def color-cyan    "#3B9AFF")

;; Backgrounds (bg-1: cards, bg-2: page, bg-3: warm surface)
(def bg-card    "#FFFFFF")
(def bg-main    "#F6F6F6")
(def bg-surface "#F7F3EB")
(def bg-hover   "#F0EFEB")
(def bg-active  "#E8E7E2")
(def bg-subtle  "#F6F6F6")

;; Borders
(def border-default "#E2E1DF")
(def border-hover   "#BCBAB5")

;; Foreground hierarchy
(def text-primary   "#000000")
(def text-secondary "#3C404A")
(def text-tertiary  "#6B6663")
(def text-disabled  "#BCBAB5")

;; Beige palette
(def beige-700 "#6B6663")
(def beige-500 "#DDD6D0")
(def beige-300 "#E6D9C2")
(def beige-100 "#F7F3EB")

;; Overlay
(def overlay "rgba(6, 13, 65, 0.55)")

;; Semantic — feedback
;; Naming differs from CSS vars: here `light` matches CSS `--*-lightest` (the
;; pale tint used as a badge background) and `dark` matches CSS `--*-text`
;; (the AA-compliant text color used on that background). The saturated brand
;; fills (CSS `--*-dark`) live as `*-default` below.
(def success-default "#17A66D")
(def success-light   "#D4F8E7")
(def success-dark    "#0F7C50")

(def warning-default "#FFB033")
(def warning-light   "#FFEEC2")
;; Bumped from #9A6B0F (4.07:1 — failed AA) to #7A5410 (~5.9:1 on warning-light).
(def warning-dark    "#7A5410")

(def error-default "#F04646")
(def error-light   "#FFDEDE")
(def error-dark    "#B91C1C")

;; Complementary (charts and accent illustrations)
(def blue-700      "#1527A9")
(def blue-500      "#3370D1")
(def blue-300      "#A2CEFF")
(def purple-700    "#8B3ADD")
(def purple-300    "#D2B5F5")
(def pink-500      "#FE7B9D")
(def pink-200      "#FFCBDB")
(def peach-400     "#FFA28D")
(def peach-200     "#FFD3C7")

(def chart-colors [blue-500 purple-700 pink-500 peach-400 success-default warning-default])

;; ============================================
;; SPACING — 8px grid
;; ============================================

(def spacing
  {:0 "0"
   :1 "4px"
   :2 "8px"
   :3 "16px"
   :4 "24px"
   :5 "32px"
   :6 "48px"
   :7 "64px"
   :8 "128px"})

(defn sp [key] (get spacing key "0"))

(def padding
  {:xs   "4px"
   :sm   "8px"
   :md   "16px"
   :lg   "24px"
   :xl   "24px 24px"
   :card "24px"})

;; ============================================
;; TYPOGRAPHY
;; ============================================

;; Default font-family used by inline styles (body copy).
;; Headings/labels can opt-in to font-display, font-heading, font-ui, font-mono.
(def font-family   "'Work Sans', system-ui, -apple-system, sans-serif")
(def font-display  "'DM Serif Display', Georgia, serif")
(def font-heading  "'Poppins', system-ui, sans-serif")
(def font-body     "'Work Sans', system-ui, sans-serif")
(def font-ui       "'Manrope', 'Work Sans', system-ui, sans-serif")
(def font-mono     "'IBM Plex Mono', ui-monospace, Menlo, monospace")

(def font-sizes
  {:xs   "12px"
   :sm   "14px"
   :base "16px"
   :lg   "18px"
   :xl   "20px"
   :2xl  "24px"
   :3xl  "30px"
   :4xl  "36px"})

(def font-weights
  {:regular  "400"
   :medium   "500"
   :semibold "600"
   :bold     "700"})

(def line-heights
  {:tight  "1.2"
   :normal "1.5"
   :loose  "1.75"})

;; ============================================
;; BREAKPOINTS
;; ============================================

(def breakpoints
  {:sm "576px"
   :md "768px"
   :lg "960px"
   :xl "1140px"})

;; ============================================
;; BORDERS & SHADOWS
;; ============================================

(def border-radius
  {:sm   "8px"
   :md   "12px"
   :lg   "16px"
   :xl   "24px"
   :full "9999px"})

(def shadows
  {:sm   "0 1px 2px rgba(0,0,0,.06)"
   :md   "0 0 2px rgba(0,0,0,.20),0 2px 15px rgba(0,0,0,.08)"
   :lg   "0 0 4px rgba(0,0,0,.05),0 8px 40px rgba(0,0,0,.10)"
   :card "0 1px 2px rgba(0,0,0,.06)"
   :hover "0 1px 1px rgba(0,0,0,.05),0 0 0 1px #BCBAB5 inset"})

;; ============================================
;; TRANSITIONS
;; ============================================

(def ease "cubic-bezier(.2,0,0,1)")
(def transition-fast    (str "160ms " ease))
(def transition-default (str "200ms " ease))
