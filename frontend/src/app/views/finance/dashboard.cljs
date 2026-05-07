(ns app.views.finance.dashboard
  (:require [clojure.string :as str]
            [reagent.core :as r]
            [re-frame.core :as rf]
            [app.ds.layout :as layout]
            [app.ds.tokens :as t]
            [app.auth.subs]
            [app.utils.format :as fmt]))

;; Finance dashboard — three editorial rows.
;; Row 1: Potencial a pagar · Comissão Paga · A apurar
;; Row 2: Comissão x Agenciamento (split numerics + 6-month trend)
;; Row 3: Fluxo de Caixa Projetado (30/60/90 horizons + chart)
;; Renders only data returned by the API; empty states stand in until the
;; backend has values to show.

(defn- ->num
  "Coerce strings/numbers to a JS number; nil/empty/NaN → nil."
  [v]
  (when (some? v)
    (let [n (cond
              (number? v) v
              (string? v) (let [s (str/trim v)]
                            (when-not (str/blank? s) (js/Number s)))
              :else nil)]
      (when (and (some? n) (js/isFinite n)) n))))

(defn- series-vector [v]
  (if (sequential? v) (vec v) []))

(defn- safe-map [v]
  (if (map? v) v {}))

(defn- brl-value
  "DM Serif Display number with the R$ prefix in UI font (or fallback when nil)."
  [v fallback]
  (if-let [n (->num v)]
    [:<> [:span.currency "R$"] (or (fmt/int-brl n) fallback)]
    fallback))

(defn- chart-empty [label]
  [:div {:style {:padding "32px" :text-align "center" :color "var(--fg-3)"
                 :font-family "var(--font-mono)" :font-size "12px"}}
   label])

(defn- period-suffix
  "Mono caption fragment for the active period, e.g. 'Q2 · 2026' or 'histórico'."
  [{:keys [year quarter]}]
  (let [year-label (if (and (string? year) (str/ends-with? year "_plus"))
                     (str (first (str/split year #"_")) "+")
                     (str year))]
    (cond
      (and (= :all year) (= :all quarter)) "histórico"
      (and (not= :all year) (= :all quarter)) year-label
      (and (= :all year) (not= :all quarter)) (str "Q" quarter)
      :else (str "Q" quarter " · " year-label))))

(defn- format-asof
  "Format an ISO timestamp into 'dd mmm yyyy, hh:mm' in lowercase pt-BR."
  [iso]
  (when (and iso (string? iso))
    (try
      (let [d (js/Date. iso)]
        (when-not (js/isNaN (.getTime d))
          (-> (.toLocaleString d "pt-BR"
                               #js {:day "2-digit" :month "short" :year "numeric"
                                    :hour "2-digit" :minute "2-digit"})
              (.toLowerCase)
              (.replace "." ""))))
      (catch :default _ nil))))

;; ----- pt-BR axis helpers ---------------------------------------------

(def ^:private pt-months
  ["jan" "fev" "mar" "abr" "mai" "jun"
   "jul" "ago" "set" "out" "nov" "dez"])

(defn- pt-month
  "1 → 'jan', 12 → 'dez'. Returns nil on out-of-range."
  [m]
  (when (and (number? m) (<= 1 m 12))
    (nth pt-months (dec m))))

(defn- ym-parts
  "'2026-05' → {:y 2026 :m 5 :q 2}. Returns nil on malformed input."
  [ym]
  (when (and (string? ym) (= 7 (count ym)))
    (let [y (js/parseInt (subs ym 0 4) 10)
          m (js/parseInt (subs ym 5 7) 10)]
      (when (and (not (js/isNaN y)) (not (js/isNaN m))
                 (<= 1 m 12))
        {:y y :m m :q (inc (quot (dec m) 3))}))))

(defn- parse-pt-label
  "Fallback parser for the 'mai/26' shape when :ym is absent.
   Returns {:y 26 :m 5} as integers (year is 2-digit only)."
  [s]
  (when (and (string? s) (re-find #"^[a-z]{3}/\d{2}$" s))
    (let [[mon yr] (str/split s #"/")
          midx (.indexOf pt-months mon)]
      (when (>= midx 0)
        {:y (+ 2000 (js/parseInt yr 10))
         :m (inc midx)
         :q (inc (quot midx 3))}))))

(defn- point-parts
  "Extracts {:y :m :q} from a series point, preferring :ym (full year)
   and falling back to the 'mai/26' label."
  [p]
  (or (ym-parts (:ym p)) (parse-pt-label (:label p))))

(defn- horizon-closing-month
  "'fecha jun/26' style label for the month landing N days from today.
   Used by the horizon strip to anchor each window to a real month."
  [days]
  (let [d (js/Date.)]
    (.setDate d (+ (.getDate d) days))
    (str (pt-month (inc (.getMonth d)))
         "/"
         (.padStart (str (mod (.getFullYear d) 100)) 2 "0"))))

;; ----- Row 1: KPI cards ------------------------------------------------
;; Potencial a pagar = A apurar + Projetado, restricted to policies still
;;   inside their 12-month commission lifecycle.
;; Comissão Paga     = Σ policies.total_paid_comissao + total_paid_agenciamento.
;; A apurar           = imported, matched, non-locked monthly competencies.

(defn- kpi-potencial [{:keys [value caption]}]
  [:div.kpi
   [:div.kpi-label
    [layout/icon "target" {:width 14 :height 14}]
    "potencial a pagar"]
   [:div.kpi-value (brl-value value "·")]
   [:div.kpi-foot
    [:span (or caption "a apurar + projetado, sem valores realizados")]]
   [:svg.kpi-grafismo {:style {:color "var(--beige-light)"}}
    [:use {:href "#i-grafismo"}]]])

(defn- kpi-paga [{:keys [value caption]}]
  [:div.kpi
   [:div.kpi-label
    [layout/icon "check" {:width 14 :height 14}]
    "comissão paga"]
   [:div.kpi-value (brl-value value "·")]
   [:div.kpi-foot
    [:span (or caption "comissão + agenciamento já realizados")]]])

(defn- kpi-a-apurar [{:keys [value caption]}]
  [:div.kpi
   [:div.kpi-label
    [layout/icon "money" {:width 14 :height 14}]
    "a apurar"]
   [:div.kpi-value (brl-value value "·")]
   [:div.kpi-foot
    [:span (or caption "NF importada e ainda não realizada")]]
   [:svg.kpi-grafismo {:style {:color "var(--neutral-light)"}}
    [:use {:href "#i-grafismo-listras"}]]])

(defn- dashboard-error-callout [message]
  [:div.callout.finance-error {:role "alert"}
   [layout/icon "alert" {:width 20 :height 20}]
   [:div
    [:strong "Atualização interrompida"]
    [:p message]
    [:button.btn.btn-secondary.btn-sm
     {:type "button"
      :on-click #(rf/dispatch [:finance/fetch-dashboard])}
     "Tentar atualizar de novo"]]])

;; ----- Shared chart helpers --------------------------------------------

(defn- fmt-axis-val
  "Compact Y-axis label: 0 → '0', 50000 → '50k', 1500000 → '1.5M'."
  [v]
  (cond
    (zero? v) "0"
    (>= v 1000000) (let [m (/ v 1000000)]
                     (if (== m (js/Math.round m))
                       (str (js/Math.round m) "M")
                       (str (.toFixed m 1) "M")))
    (>= v 1000)    (let [k (/ v 1000)]
                     (if (== k (js/Math.round k))
                       (str (js/Math.round k) "k")
                       (str (.toFixed k 1) "k")))
    :else (str (js/Math.round v))))

(defn- tooltip-label [p kind v]
  (str (or (:label p) "sem mês") " · " kind " · " (or (fmt/fmt-brl (->num v)) "R$ 0,00")))

;; ----- Row 2: Comissão x Agenciamento ---------------------------------

(defn- proportion-strip [comissao agenciamento]
  (let [c (or (->num comissao) 0)
        a (or (->num agenciamento) 0)
        total (+ c a)
        com-pct (if (pos? total) (* 100 (/ c total)) 0)
        ag-pct  (if (pos? total) (* 100 (/ a total)) 0)]
    [:div.proportion-strip
     [:div.seg.primary {:style {:width (str com-pct "%")}}]
     [:div.seg.beige   {:style {:width (str ag-pct "%")}}]]))

(defn- chart-comissao-agenciamento [data]
  (if (empty? (series-vector data))
    [:div.series-fallback
     [:div.lab "histórico mensal"]
     [:strong "nenhum mês com comissão ou agenciamento"]
     [:span "os totais acima seguem válidos; o filtro não trouxe uma série mensal para comparar"]]
    (let [pts (series-vector data)
          n   (count pts)

          ;; Chart region inside viewBox 700×260
          lft 76  rgt 660  tp 16  btm 210  lbl-y 232
          cw  (- rgt lft)
          ch  (- btm tp)
          slot (/ cw (max 1 n))

          ;; Collect all non-nil numeric values for Y range
          all-v (->> pts
                     (mapcat (fn [p] [(:comissao p) (:agenciamento p)]))
                     (keep ->num))
          raw-max (if (seq all-v) (reduce max all-v) 1)

          ;; Nice Y-axis ticks (~4 divisions)
          safe    (max 1 raw-max)
          mag     (js/Math.pow 10 (js/Math.floor (js/Math.log10 safe)))
          norm    (/ safe mag)
          step    (* mag (cond (<= norm 1.5) 0.5
                               (<= norm 3)   1
                               (<= norm 7)   2
                               :else          5))
          y-ceil  (* step (js/Math.ceil (/ safe step)))
          ticks   (loop [v 0 acc []]
                    (if (> v (+ y-ceil 0.01)) acc (recur (+ v step) (conj acc v))))
          yf      (fn [v] (- btm (* (/ (or v 0) y-ceil) ch)))]

      [:svg.chart.chart-comissao
       {:viewBox "0 0 700 260"
        :preserveAspectRatio "none"
        :role "img"
        :aria-label "Comissão e agenciamento realizados por mês"}
       [:desc "Barras pretas mostram comissão realizada. Barras bege mostram agenciamento realizado."]
       ;; Y-axis grid lines + labels
       [:g
        (for [tv ticks]
          ^{:key (str "y" tv)}
          [:g
           [:line {:x1 lft :y1 (yf tv) :x2 rgt :y2 (yf tv)
                   :stroke t/border-default :stroke-width 1}]
           [:text {:x (- lft 8) :y (+ (yf tv) 3.5) :text-anchor "end"
                   :font-family t/font-mono :font-size 10
                   :fill t/text-disabled :letter-spacing "0.02em"}
            (fmt-axis-val tv)]])]

       ;; Bars
       [:g
        (for [[i p] (map-indexed vector pts)
              :let [base (+ lft 12 (* i slot))]]
          ^{:key (str "g" i)}
          [:g
           (when-let [cv (->num (:comissao p))]
             [:rect {:x base :y (yf cv)
                     :width 18 :height (max 1 (- btm (yf cv)))
                     :fill t/color-primary :rx 2}])
           (when-let [av (->num (:agenciamento p))]
             [:rect {:x (+ base 22) :y (yf av)
                     :width 18 :height (max 1 (- btm (yf av)))
                     :fill t/beige-300 :rx 2}])])]

       ;; X-axis labels
       [:g {:font-family t/font-mono :font-size 10
            :fill t/text-tertiary :text-anchor "middle" :letter-spacing "0.02em"}
        (for [[i p] (map-indexed vector pts)]
          ^{:key (str "x" i)}
          [:text {:x (+ lft 32 (* i slot)) :y lbl-y} (or (:label p) "sem mês")])]])))

(defn- comissao-agenciamento-card [{:keys [comissao agenciamento series period]}]
  (let [c (or (->num comissao) 0)
        a (or (->num agenciamento) 0)
        total (+ c a)
        com-pct (when (pos? total) (* 100 (/ c total)))
        ag-pct  (when (pos? total) (* 100 (/ a total)))]
    [:div.card.finance-revenue-card
     [:div.card-head
      [:div [:h3 "Comissão x Agenciamento"]
       [:div.card-sub (or period "valores realizados em todo o histórico")]]]
     [:div.split-numerics
      [:div.col
       [:div.lab "comissão"]
       [:div.num (brl-value comissao "·")]
       [:div.lab (if com-pct (str (.toFixed com-pct 1) "% do total") "—")]]
      [:div.rule]
      [:div.col
       [:div.lab "agenciamento"]
       [:div.num (brl-value agenciamento "·")]
       [:div.lab (if ag-pct (str (.toFixed ag-pct 1) "% do total") "—")]]]
     [proportion-strip comissao agenciamento]
     [:div.legend
      [:span.legend-dot {:style {:color "var(--black)"}} "comissão"]
      [:span.legend-dot {:style {:color "var(--beige-light)"}} "agenciamento"]]
     [chart-comissao-agenciamento series]]))

;; ----- Row 3: Fluxo de Caixa Projetado --------------------------------

(defn- trim-fluxo-series
  "Drop leading and trailing months that have no data on either series.
   Keeps the chart focused on the months that actually carry signal."
  [series]
  (let [has-data? (fn [p] (or (some? (->num (:realizado p)))
                              (some? (->num (:a_apurar p)))
                              (some? (->num (:projetado p)))))]
    (->> (series-vector series)
         (drop-while (complement has-data?))
         reverse
         (drop-while (complement has-data?))
         reverse
         vec)))

(defn- today-index
  "Index of the current calendar month. Returns nil when the filter hides it."
  [pts]
  (some (fn [[i p]] (when (:is_current_month p) i))
        (map-indexed vector pts)))

(defn- projected-points
  "Projected points after chart trimming, preserving the index used by the SVG."
  [series]
  (->> (trim-fluxo-series series)
       (map-indexed (fn [i p]
                      (when-let [v (->num (:projetado p))]
                        {:index i :point p :value v})))
       (keep identity)
       vec))

(defn- default-projected-index [series]
  (let [pts (trim-fluxo-series series)
        today-i (today-index pts)
        projected (projected-points series)]
    (or (when (and today-i (some #(= today-i (:index %)) projected))
          today-i)
        (:index (first projected)))))

(defn- smooth-d
  "Catmull-Rom → cubic-bezier open path through [[x y] …] pts. tension 0..1."
  [pts tension]
  (let [n (count pts)
        t tension
        gp (fn [i]
             (cond
               (neg? i)  (let [[x0 y0] (first pts) [x1 y1] (second pts)]
                           [(- (* 2 x0) x1) (- (* 2 y0) y1)])
               (>= i n)  (let [[xn yn] (peek pts) [xp yp] (nth pts (- n 2))]
                           [(- (* 2 xn) xp) (- (* 2 yn) yp)])
               :else     (nth pts i)))]
    (when (>= n 2)
      (str "M " (first (first pts)) " " (second (first pts)) " "
           (str/join " "
             (for [i (range (dec n))
                   :let [[p0x p0y] (gp (dec i))
                         [p1x p1y] (gp i)
                         [p2x p2y] (gp (inc i))
                         [p3x p3y] (gp (+ i 2))
                         c1x (+ p1x (* t (/ (- p2x p0x) 2)))
                         c1y (+ p1y (* t (/ (- p2y p0y) 2)))
                         c2x (- p2x (* t (/ (- p3x p1x) 2)))
                         c2y (- p2y (* t (/ (- p3y p1y) 2)))]]
               (str "C " c1x " " c1y " " c2x " " c2y " " p2x " " p2y)))))))

(defn- chart-fluxo-caixa
  "Forecast chart — projected receivables across the next 12 months.
   The current month sits inside a quiet beige band labeled 'mês atual';
   a thin dashed rule marks today's exact position. Only the projected line
   carries the data, supported by a soft area gradient and small dots that
   mark each monthly value. Hover surfaces a dark editorial pill with the
   month label and serif value."
  ([data] (chart-fluxo-caixa data nil))
  ([data {:keys [selected-index on-select]}]
  (let [pts (trim-fluxo-series data)]
    (if (empty? pts)
      [chart-empty "Sem fluxo de caixa para o período"]
      (let [n   (count pts)
            vb-w 1000  vb-h 420
            lft 56   rgt 980   tp 28    btm 350
            lbl-y 384
            cw  (- rgt lft)
            ch  (- btm tp)

            x-step (/ cw (max 1 (dec n)))
            xf     (fn [i] (+ lft (* i x-step)))

            all-v (->> pts
                       (mapcat (fn [p] [(:realizado p) (:a_apurar p) (:projetado p)]))
                       (keep ->num))
            raw-max (if (seq all-v) (reduce max all-v) 1)

            safe    (max 1 raw-max)
            mag     (js/Math.pow 10 (js/Math.floor (js/Math.log10 safe)))
            norm    (/ safe mag)
            step    (* mag (cond (<= norm 1.5) 0.5
                                 (<= norm 3)   1
                                 (<= norm 7)   2
                                 :else          5))
            y-ceil  (* step (js/Math.ceil (/ safe step)))
            ticks   (loop [v 0 acc []]
                      (if (> v (+ y-ceil 0.01)) acc (recur (+ v step) (conj acc v))))
            yf      (fn [v] (- btm (* (/ (or v 0) y-ceil) ch)))

            label-nth (cond (> n 14) 3 (> n 8) 2 :else 1)

            ;; Today anchor — current month band + dashed today rule.
            ;; The band represents the current month period: from today's
            ;; data point forward to the next one (visually a full month
            ;; chunk). The dashed rule marks today's exact day-of-month
            ;; position inside that band.
            today-i  (today-index pts)
            today-x  (when today-i (xf today-i))
            today-fraction (when today-i
                             (let [d (js/Date.)
                                   day (.getDate d)
                                   last-day (.getDate (js/Date. (.getFullYear d) (inc (.getMonth d)) 0))]
                               (max 0 (min 1 (/ (dec day) (max 1 (dec last-day)))))))
            band-x0  (when today-x (max lft today-x))
            band-x1  (when today-x (min rgt (+ today-x x-step)))
            today-rule-x (when (and band-x0 band-x1 today-fraction)
                           (+ band-x0 (* (- band-x1 band-x0) today-fraction)))

            proj-xy (->> pts
                         (map-indexed (fn [i p]
                                        (when-let [v (->num (:projetado p))]
                                          [i (xf i) (yf v) v p])))
                         (keep identity)
                         vec)]

        (if (empty? proj-xy)
          [chart-empty "Sem valores projetados para desenhar no período"]
          (let [line-d (smooth-d (mapv (fn [[_ x y _ _]] [x y]) proj-xy) 0.35)

            area-d (when (seq proj-xy)
                     (let [base (smooth-d (mapv (fn [[_ x y _ _]] [x y]) proj-xy) 0.35)
                           [_ last-x _ _ _] (peek proj-xy)
                           [_ first-x _ _ _] (first proj-xy)]
                       (str base " L " last-x " " btm
                            " L " first-x " " btm " Z")))
            selected-entry (some (fn [[i :as entry]]
                                   (when (= i selected-index) entry))
                                 proj-xy)]

        [:svg.chart.chart-fluxo
         {:viewBox (str "0 0 " vb-w " " vb-h)
          :preserveAspectRatio "none"
          :role "img"
          :aria-label "Fluxo de caixa projetado por competência mensal"}
         [:desc "Linha e área mostram valores projetados. A faixa vertical marca o mês atual."]

         [:defs
          [:linearGradient {:id "fluxo-projetado-fill" :x1 "0" :y1 "0" :x2 "0" :y2 "1"}
           [:stop {:offset "0%" :stop-color "var(--blue-light)" :stop-opacity 0.32}]
           [:stop {:offset "60%" :stop-color "var(--blue-light)" :stop-opacity 0.08}]
           [:stop {:offset "100%" :stop-color "var(--blue-light)" :stop-opacity 0}]]
          [:filter {:id "fluxo-tooltip-shadow" :x "-20%" :y "-20%" :width "140%" :height "150%"}
           [:feDropShadow {:dx 0 :dy 6 :stdDeviation 8 :flood-color "var(--fg-1)" :flood-opacity 0.18}]]
          [:clipPath {:id "fluxo-plot-clip"}
           [:rect {:x lft :y tp :width cw :height ch :rx 8}]]]

         ;; Chart frame — flat surface with 1px border, per Editorial Ledger
         [:rect {:x lft :y tp :width cw :height ch :rx 8
                 :fill "var(--bg-1)"
                 :stroke "var(--border-subtle)"
                 :stroke-width 1
                 :vector-effect "non-scaling-stroke"}]

         ;; Current month band — quiet beige paper highlight
         (when (and band-x0 band-x1 (> band-x1 band-x0))
           [:g.fluxo-month-band
            [:rect {:x band-x0 :y tp
                    :width (- band-x1 band-x0)
                    :height ch
                    :fill "var(--beige-lightest)"
                    :clip-path "url(#fluxo-plot-clip)"}]
            ;; Editorial label inside the band, top-left
            [:rect {:x (+ band-x0 8) :y (+ tp 8)
                    :width 70 :height 20 :rx 6
                    :fill "var(--bg-1)"
                    :stroke "var(--beige-light)"
                    :stroke-width 1
                    :vector-effect "non-scaling-stroke"}]
            [:text {:x (+ band-x0 16) :y (+ tp 22)
                    :font-family "IBM Plex Mono, monospace"
                    :font-size 10 :fill "var(--fg-2)"
                    :letter-spacing "0.04em"}
             "mês atual"]])

         ;; Y-axis grid — uniform dashed lines, mono labels
         [:g
          (for [tv ticks]
            ^{:key (str "y" tv)}
            [:g
             [:line {:x1 lft :y1 (yf tv) :x2 rgt :y2 (yf tv)
                     :stroke "var(--border-subtle)"
                     :stroke-width 1
                     :vector-effect "non-scaling-stroke"
                     :stroke-opacity (if (zero? tv) 0.85 0.55)
                     :stroke-dasharray (when (pos? tv) "2 5")}]
             [:text {:x (- lft 10) :y (+ (yf tv) 3.5) :text-anchor "end"
                     :font-family "IBM Plex Mono, monospace" :font-size 10.5
                     :fill "var(--fg-3)" :letter-spacing "0.02em"}
              (fmt-axis-val tv)]])]

         ;; Today rule — dashed vertical line at today's exact position
         (when today-rule-x
           [:line.fluxo-today-rule
            {:x1 today-rule-x :y1 (+ tp 4) :x2 today-rule-x :y2 btm
             :stroke "var(--fg-2)" :stroke-width 1
             :stroke-dasharray "3 4"
             :stroke-opacity 0.55
             :vector-effect "non-scaling-stroke"}])

         (when selected-entry
           (let [[_ sx sy _ _] selected-entry]
             [:g.chart-crosshair
              [:line {:x1 lft :y1 sy :x2 rgt :y2 sy
                      :stroke "var(--fg-2)" :stroke-width 1
                      :stroke-dasharray "2 5"
                      :stroke-opacity 0.34
                      :vector-effect "non-scaling-stroke"}]
              [:line {:x1 sx :y1 tp :x2 sx :y2 btm
                      :stroke "var(--fg-2)" :stroke-width 1
                      :stroke-dasharray "3 5"
                      :stroke-opacity 0.44
                      :vector-effect "non-scaling-stroke"}]]))

         ;; Projected area
         (when area-d
           [:path.proj-area
            {:d area-d
             :fill "url(#fluxo-projetado-fill)"
             :clip-path "url(#fluxo-plot-clip)"}])

         ;; Projected line — blue-regular for clean editorial weight
         (when line-d
           [:path.proj-line
            {:d line-d :fill "none" :stroke "var(--blue-regular)"
             :stroke-width 2 :stroke-linecap "round"
             :stroke-linejoin "round"
             :clip-path "url(#fluxo-plot-clip)"
             :vector-effect "non-scaling-stroke"}])

         ;; Projected dots — small, dark blue with white halo
         [:g.proj-dots {:clip-path "url(#fluxo-plot-clip)"}
          (for [[i px py _ _] proj-xy]
            ^{:key (str "pd" i)}
            [:circle.proj-dot
             {:cx px :cy py :r 3
              :fill "var(--blue-regular)"
              :stroke "var(--bg-1)" :stroke-width 1.5
              :style {"--dot-i" (str i)}}])]

         ;; Hover hit zones + dark editorial tooltip
         [:g
          (for [[i px py v p] proj-xy
                :let [label (tooltip-label p "projetado" v)
                      selected? (= i selected-index)
                      tip-w 138
                      tip-h 50
                      tip-x (cond
                              (> px (- vb-w 168)) (- px tip-w 18)
                              (< px (+ lft 56)) (+ px 18)
                              :else (+ px 14))
                      tip-y (max (+ tp 4) (- py 14))]]
            ^{:key (str "d" i)}
            [:g.chart-point
             {:class (str "chart-point" (when selected? " selected"))
              :tabIndex 0
              :role "button"
              :aria-label label
              :aria-pressed selected?
              :on-mouse-enter #(when on-select (on-select i))
              :on-focus #(when on-select (on-select i))
              :on-click #(when on-select (on-select i))
              :on-key-down (fn [e]
                              (when (#{"Enter" " "} (.-key e))
                                (.preventDefault e)
                                (when on-select (on-select i))))}
             [:circle.chart-point-hit {:cx px :cy py :r 18}]
             [:circle.chart-point-active
              {:cx px :cy py :r 5
               :fill "var(--bg-1)"
               :stroke "var(--blue-regular)" :stroke-width 2}]
             [:g.chart-tooltip
              [:rect {:x tip-x :y tip-y :width tip-w :height tip-h :rx 8
                      :fill "var(--fg-1)"
                      :filter "url(#fluxo-tooltip-shadow)"}]
              [:text.month {:x (+ tip-x 12) :y (+ tip-y 19)}
               (:label p)]
              [:text.value {:x (+ tip-x 12) :y (+ tip-y 38)}
               (or (fmt/fmt-brl v) "R$ 0,00")]]])]

         ;; X-axis labels — clean lowercase mono, the backend's mai/26 format
         [:g {:font-family "IBM Plex Mono, monospace" :font-size 10.5
              :fill "var(--fg-3)" :text-anchor "middle" :letter-spacing "0.02em"}
          (for [[i p] (map-indexed vector pts)
                :when (zero? (mod i label-nth))]
            ^{:key (str "x" i)}
            [:text {:x (xf i) :y lbl-y} (or (:label p) "sem mês")])]])))))))

(defn- horizon-card
  "30/60/90d horizon as a self-contained editorial card.
   Top: mono lowercase label.
   Middle: serif amount.
   Bottom: mono apólice count."
  [{:keys [label value detail closing]}]
  [:div.horizon-card
   [:div.horizon-card-head
    [:span.lab label]
    (when closing [:span.horizon-card-close closing])]
   [:div.horizon-card-num (brl-value value "·")]
   [:div.horizon-card-foot
    (when detail [:span.meta detail])]])

(defn- summary-col [{:keys [label value detail]}]
  [:div.col
   [:div.lab label]
   [:div.num (if (= :count (:kind value))
               (:text value)
               (brl-value value "·"))]
   (when detail [:div.meta detail])])

(defn- inspector-metric [{:keys [label value muted?]}]
  [:div.inspector-metric
   [:span label]
   [:strong {:class (when muted? "muted")}
    (if (some? value) (fmt/fmt-brl-int value) "·")]])

(defn- fluxo-inspector-panel
  "Side rail for the selected projected month. It keeps the chart inspectable
   without opening a modal or forcing users into the data table."
  [{:keys [entry total]}]
  (let [{:keys [index point value]} entry
        parts (point-parts point)
        quarter (:q parts)
        year (:y parts)
        realized (->num (:realizado point))
        a-apurar (->num (:a_apurar point))
        projected value]
    [:aside.cash-flow-inspector
     {:aria-label "Competência selecionada no fluxo de caixa"}
     [:div.inspector-eyebrow
      [:span "competência em foco"]
      (when (and index total)
        [:span (str (inc index) "/" total)])]
     [:div.inspector-month
      [:strong (:label point)]
      (when (and quarter year)
        [:span (str "Q" quarter " · " year)])]
     [:div.inspector-total
      [:span "projetado"]
      [:strong (brl-value projected "·")]]
     [:div.inspector-metrics
      [inspector-metric {:label "a apurar" :value a-apurar}]
      [inspector-metric {:label "realizado" :value realized :muted? true}]]
     [:div.inspector-note
      "Use Tab no gráfico para escolher outro mês."]]))

(defn- chart-fluxo-caixa-table
  "Tabular alternative to the cash-flow SVG chart. Wrapped in <details> so
   sighted users can disclose it on demand; screen readers read the table
   regardless. Renders only rows that carry at least one numeric value."
  [series]
  (let [rows (filter (fn [p] (or (->num (:realizado p))
                                 (->num (:a_apurar p))
                                 (->num (:projetado p))))
                     (series-vector series))]
    (when (seq rows)
      [:details.chart-data-table
       [:summary "Ver dados em tabela"]
       [:div.table-wrap
        [:table.table
         [:caption.sr-only
          "Fluxo de caixa mensal por competência: realizado, a apurar e projetado em reais."]
         [:thead
          [:tr
           [:th {:scope "col"} "Mês"]
           [:th.right {:scope "col"} "Realizado"]
           [:th.right {:scope "col"} "A apurar"]
           [:th.right {:scope "col"} "Projetado"]]]
         [:tbody
          (for [[i p] (map-indexed vector rows)]
            ^{:key (or (:ym p) (:label p) (str "fluxo-row-" i))}
            [:tr
             [:th {:scope "row"} (or (:label p) "sem mês")]
             [:td.right.num (or (fmt/fmt-brl-int (:realizado p)) "·")]
             [:td.right.num (or (fmt/fmt-brl-int (:a_apurar p)) "·")]
             [:td.right.num (or (fmt/fmt-brl-int (:projetado p)) "·")]])]]]])))

(defn- fluxo-caixa-card [{:keys [horizon period-summary filtered? series as-of]}]
  (r/with-let [selected-index* (r/atom nil)]
    (let [projected-count (:apolices period-summary)
          projected (projected-points series)
          fallback-index (default-projected-index series)
          selected-index (or @selected-index* fallback-index)
          selected-entry (or (some #(when (= selected-index (:index %)) %) projected)
                             (first projected))
          active-index (:index selected-entry)
          horizon-months (count projected)]
      [:div.card.fluxo-card
       [:div.card-head
        [:div [:h3 "Fluxo de caixa projetado"]
         [:div.card-sub "competência mensal; projetado entra no potencial a pagar"]]
        (when as-of [:span.card-asof (str "atualizado " as-of)])]
       (if filtered?
         [:div.horizon-strip.period-summary
          [summary-col {:label "realizado no período"
                        :value (:realizado period-summary)}]
          [summary-col {:label "a apurar no período"
                        :value (:a_apurar period-summary)}]
          [summary-col {:label "projetado no período"
                        :value (:projetado period-summary)}]
          [summary-col {:label "apólices projetadas"
                        :value {:kind :count :text (str (or projected-count 0))}
                        :detail "com parcelas no período"}]]
         [:div.horizon-cards
          [horizon-card {:label "próximos 30d"
                         :value (:next_30 horizon)
                         :closing (str "fecha " (horizon-closing-month 30))
                         :detail (when-let [n (:next_30_apolices horizon)]
                                   (str n (if (= n 1) " apólice" " apólices")))}]
          [horizon-card {:label "próximos 60d"
                         :value (:next_60 horizon)
                         :closing (str "fecha " (horizon-closing-month 60))
                         :detail (when-let [n (:next_60_apolices horizon)]
                                   (str n (if (= n 1) " apólice" " apólices")))}]
          [horizon-card {:label "próximos 90d"
                         :value (:next_90 horizon)
                         :closing (str "fecha " (horizon-closing-month 90))
                         :detail (when-let [n (:next_90_apolices horizon)]
                                   (str n (if (= n 1) " apólice" " apólices")))}]])
       [:div.chart-frame
        [:div.chart-legend
         [:span.legend-line "projetado"]
         [:span.legend-month-chip "mês atual"]
         (when (and (not filtered?) (pos? horizon-months))
           [:span.legend-horizon
            "horizonte " [:strong (str horizon-months)] " "
            (if (= 1 horizon-months) "mês" "meses")])]
        [:div.chart-command-surface
         [:div.chart-pane
          [chart-fluxo-caixa series
           {:selected-index active-index
            :on-select #(reset! selected-index* %)}]
          [chart-fluxo-caixa-table series]]
         (when selected-entry
           [fluxo-inspector-panel {:entry selected-entry
                                   :total horizon-months}])]]])))

;; ----- Topbar period control ------------------------------------------

(defn- period-select
  "Two compact selects (year + quarter). Each defaults to \"Todos\"
   (all-time). Dispatches :finance/set-period on change."
  [{:keys [year quarter years future-year-floor]}]
  (let [on-change (fn [kind]
                    (fn [e]
                      (let [v (.. e -target -value)]
                        (rf/dispatch [:finance/set-period kind
                                      (cond
                                        (= v "all") :all
                                        (str/ends-with? v "_plus") v
                                        :else (js/parseInt v 10))]))))
        future-value (when future-year-floor (str future-year-floor "_plus"))
        reset? (or (not= :all year) (not= :all quarter))]
    [:div.period-control {:role "group" :aria-label "Filtro de período"}
     [:span.period-label "período"]
     [:select.period-select {:value (if (= year :all) "all" (str year))
                             :on-change (on-change :year)
                             :aria-label "Ano"}
      [:option {:value "all"} "Todos os anos"]
      (for [y (or years [])]
        ^{:key y} [:option {:value (str y)} (str y)])
      (when future-value
        [:option {:value future-value} (str future-year-floor "+")])]
     [:select.period-select {:value (if (= quarter :all) "all" (str quarter))
                             :on-change (on-change :quarter)
                             :aria-label "Trimestre"}
      [:option {:value "all"} "Todos os trimestres"]
      [:option {:value "1"} "Q1"]
      [:option {:value "2"} "Q2"]
      [:option {:value "3"} "Q3"]
      [:option {:value "4"} "Q4"]]
     (when reset?
       [:button.period-reset
        {:type "button"
         :on-click #(rf/dispatch [:finance/reset-period])}
        "limpar"])]))

(defn finance-dashboard-page []
  (r/with-let [_ (rf/dispatch [:finance/fetch-dashboard])]
    (let [dashboard @(rf/subscribe [:finance/dashboard])
          loading?  @(rf/subscribe [:finance/loading?])
          error     @(rf/subscribe [:finance/dashboard-error])
          period    @(rf/subscribe [:finance/period])
          user      @(rf/subscribe [:auth/current-user])
          route     @(rf/subscribe [:current-route-name])

          potencial    (or (:potencial_a_pagar dashboard) (:comissao_potencial dashboard))
          paga         (:comissao_paga dashboard)
          as-of        (format-asof (:as_of dashboard))
          period-tag   (period-suffix period)

          comm-ag        (safe-map (:comissao_agenciamento dashboard))
          comissao-tot   (:comissao comm-ag)
          agenciam-tot   (:agenciamento comm-ag)
          comm-ag-series (or (:series comm-ag) [])
          comm-ag-period (:period comm-ag)

          fluxo-raw    (:fluxo_caixa dashboard)
          fluxo        (cond
                         (map? fluxo-raw) (safe-map fluxo-raw)
                         (sequential? fluxo-raw) {:series fluxo-raw}
                         :else {})
          fluxo-series (or (:series fluxo) [])
          period-summary (:period_summary fluxo)
          realized-period (:realizado period-summary)
          a-apurar-period (:a_apurar period-summary)
          projected-period (:projetado period-summary)
          open-total (or (:potencial_a_pagar period-summary) potencial)
          filtered? (or (not= :all (:year period))
                        (not= :all (:quarter period)))
          available-years (or (:available_years dashboard) [2024 2025 2026])
          future-year-floor (:future_year_floor dashboard)]
      [layout/page-shell
       {:current-route route
        :user user
        :crumbs ["plataforma rv" "finance" "dashboard"]
        :title "Visão financeira"
        :subtitle (when loading? "atualizando valores")
        :header-actions
        [[period-select {:year (:year period)
                         :quarter (:quarter period)
                         :years available-years
                         :future-year-floor future-year-floor}]]}

       [:section.finance-dashboard
        (when error
          [dashboard-error-callout error])

        ;; Row 1 — three KPIs
        [:div.kpi-grid.-three
         [kpi-potencial {:value potencial
                         :caption (str "a apurar + projetado, " period-tag)}]
         [kpi-paga      {:value paga
                         :caption (str "comissão + agenciamento realizados, " period-tag)}]
         [kpi-a-apurar  {:value a-apurar-period
                         :caption (str "NF importada sem LOCKED, " period-tag)}]]

        [:div.finance-reconciliation
         [:span "potencial a pagar"]
         [:strong (brl-value open-total "·")]
         [:span "="]
         [:span "a apurar"]
         [:strong (brl-value a-apurar-period "·")]
         [:span "+"]
         [:span "projetado"]
         [:strong (brl-value projected-period "·")]
         [:span "realizado fica fora deste total"]
         (when realized-period
           [:strong (brl-value realized-period "·")])]

        ;; Row 2 — realized split beside the larger projected cash-flow view.
        [comissao-agenciamento-card
         {:comissao comissao-tot
          :agenciamento agenciam-tot
          :series comm-ag-series
          :period comm-ag-period}]

        [fluxo-caixa-card
         {:horizon (:horizon fluxo)
          :period-summary period-summary
          :filtered? filtered?
          :series fluxo-series
          :as-of as-of}]]])))
