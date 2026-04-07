(ns app.ds.tokens)

;; ============================================
;; COLORS — Pipo Saúde Commission Platform
;; ============================================

;; Brand
(def color-primary "#000000")
(def color-white "#FFFFFF")

;; Backgrounds
(def bg-main "#F7F6F3")
(def bg-surface "#EDECE7")
(def bg-card "#FFFFFF")
(def bg-hover "#F0EFEB")
(def bg-active "#E8E7E2")

;; Borders — interactive
(def border-hover "#CACACA")

;; Grayscale — hierarchy
(def text-primary "#2B2B2B")
(def text-secondary "#6B6B6B")
(def text-disabled "#BDBDBD")
(def border-default "#E2E2E2")
(def bg-subtle "#F5F5F5")

;; Beige palette — surfaces
(def beige-700 "#6E6A63")
(def beige-500 "#C6B58A")
(def beige-300 "#E6DEC8")
(def beige-100 "#F3EFE4")

;; Overlay
(def overlay "rgba(0, 0, 0, 0.4)")

;; Semantic — feedback
(def success-default "#1FA971")
(def success-light "#D1FAE5")
(def success-dark "#15803D")

(def warning-default "#FFB703")
(def warning-light "#FEF3C7")
(def warning-dark "#B45309")

(def error-default "#EF4444")
(def error-light "#FEE2E2")
(def error-dark "#B91C1C")

;; Complementary — charts and illustrations only
(def blue-700 "#1E40AF")
(def blue-500 "#3B82F6")
(def purple-700 "#7C3AED")
(def purple-300 "#C4B5FD")
(def pink-500 "#F472B6")
(def pink-200 "#FBCFE8")
(def peach-400 "#FDBA74")
(def peach-200 "#FED7AA")

;; Chart color sequence
(def chart-colors [blue-500 purple-700 pink-500 peach-400 success-default warning-default])

;; ============================================
;; SPACING — 8px grid
;; ============================================

(def spacing
  {:0  "0"
   :1  "4px"
   :2  "8px"
   :3  "16px"
   :4  "24px"
   :5  "32px"
   :6  "48px"
   :7  "64px"
   :8  "128px"})

(defn sp [key] (get spacing key "0"))

;; Padding presets
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

(def font-family "'Inter', -apple-system, BlinkMacSystemFont, sans-serif")

(def font-sizes
  {:xs    "12px"
   :sm    "14px"
   :base  "16px"
   :lg    "18px"
   :xl    "20px"
   :2xl   "24px"
   :3xl   "30px"
   :4xl   "36px"})

(def font-weights
  {:regular  "400"
   :medium   "500"
   :semibold "600"
   :bold     "700"})

(def line-heights
  {:tight  "1.25"
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
  {:sm  "4px"
   :md  "8px"
   :lg  "12px"
   :xl  "16px"
   :full "9999px"})

(def shadows
  {:sm   "0 1px 2px rgba(0, 0, 0, 0.05)"
   :md   "0 4px 6px rgba(0, 0, 0, 0.07)"
   :lg   "0 10px 15px rgba(0, 0, 0, 0.1)"
   :card "0 1px 3px rgba(0, 0, 0, 0.08)"})

;; ============================================
;; TRANSITIONS
;; ============================================

(def transition-fast "150ms ease")
(def transition-default "250ms ease")
