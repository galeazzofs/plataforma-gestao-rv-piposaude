(ns app.views.finance.dashboard
  (:require [clojure.string :as str]
            [reagent.core :as r]
            [re-frame.core :as rf]
            [app.ds.layout :as layout]
            [app.auth.subs]
            [app.utils.format :as fmt]))

;; Finance dashboard — three editorial rows.
;; Row 1: Potencial a pagar · Comissão Paga · Obrigação aberta
;; Row 2: Comissão x Agenciamento (split numerics + 6-month trend)
;; Row 3: Fluxo de Caixa Projetado (30/60/90 horizons + chart)
;; Renders only data returned by the API; empty states stand in until the
;; backend has values to show.

(defn- ->num
  "Coerce strings/numbers to a JS number; nil/empty/NaN → nil."
  [v]
  (when (some? v)
    (let [n (if (string? v) (js/parseFloat v) v)]
      (when-not (or (nil? n) (js/isNaN n)) n))))

(defn- brl-value
  "DM Serif Display number with the R$ prefix in UI font (or fallback when nil)."
  [v fallback]
  (if (some? v)
    [:<> [:span.currency "R$"] (or (fmt/int-brl v) fallback)]
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

;; ----- Row 1: KPI cards ------------------------------------------------
;; Potencial a pagar = A apurar + Projetado, restricted to policies still
;;   inside their 12-month commission lifecycle.
;; Comissão Paga     = Σ policies.total_paid_comissao + total_paid_agenciamento.
;; Obrigação aberta  = non-realized monthly competencies in current filter.

(defn- kpi-potencial [{:keys [value caption]}]
  [:div.kpi
   [:div.kpi-label
    [layout/icon "target" {:width 14 :height 14}]
    "potencial a pagar"]
   [:div.kpi-value (brl-value value "·")]
   [:div.kpi-foot
    [:span (or caption "a apurar + projetado · exclui realizado")]]
   [:svg.kpi-grafismo {:style {:color "var(--beige-light)"}}
    [:use {:href "#i-grafismo"}]]])

(defn- kpi-paga [{:keys [value caption]}]
  [:div.kpi
   [:div.kpi-label
    [layout/icon "check" {:width 14 :height 14}]
    "comissão paga"]
   [:div.kpi-value (brl-value value "·")]
   [:div.kpi-foot
    [:span (or caption "comissão + agenciamento · histórico")]]])

(defn- kpi-saldo [{:keys [value caption]}]
  [:div.kpi
   [:div.kpi-label
    [layout/icon "money" {:width 14 :height 14}]
    "obrigação aberta"]
   [:div.kpi-value (brl-value value "·")]
   [:div.kpi-foot
    [:span (or caption "competências não realizadas · até 12 meses")]]
   [:svg.kpi-grafismo {:style {:color "var(--neutral-light)"}}
    [:use {:href "#i-grafismo-listras"}]]])

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
  (str (:label p) " · " kind " · " (or (fmt/fmt-brl v) "R$ 0,00")))

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
  (if (empty? data)
    [:div.series-fallback
     [:div.lab "histórico mensal"]
     [:strong "sem série mensal para este filtro"]
     [:span "os totais acima continuam válidos para o período selecionado"]]
    (let [pts (vec data)
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

      [:svg.chart.chart-comissao {:viewBox "0 0 700 260" :preserveAspectRatio "none"}
       ;; Y-axis grid lines + labels
       [:g
        (for [tv ticks]
          ^{:key (str "y" tv)}
          [:g
           [:line {:x1 lft :y1 (yf tv) :x2 rgt :y2 (yf tv)
                   :stroke "#E2E1DF" :stroke-width 1}]
           [:text {:x (- lft 8) :y (+ (yf tv) 3.5) :text-anchor "end"
                   :font-family "IBM Plex Mono, monospace" :font-size 10
                   :fill "#BCBAB5" :letter-spacing "0.02em"}
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
                     :fill "#000" :rx 2}])
           (when-let [av (->num (:agenciamento p))]
             [:rect {:x (+ base 22) :y (yf av)
                     :width 18 :height (max 1 (- btm (yf av)))
                     :fill "#E6D9C2" :rx 2}])])]

       ;; X-axis labels
       [:g {:font-family "IBM Plex Mono, monospace" :font-size 10
            :fill "#6B6663" :text-anchor "middle" :letter-spacing "0.02em"}
        (for [[i p] (map-indexed vector pts)]
          ^{:key (str "x" i)}
          [:text {:x (+ lft 32 (* i slot)) :y lbl-y} (:label p)])]])))

(defn- comissao-agenciamento-card [{:keys [comissao agenciamento series period]}]
  (let [c (or (->num comissao) 0)
        a (or (->num agenciamento) 0)
        total (+ c a)
        com-pct (when (pos? total) (* 100 (/ c total)))
        ag-pct  (when (pos? total) (* 100 (/ a total)))]
    [:div.card
     [:div.card-head
      [:div [:h3 "Comissão x Agenciamento"]
       [:div.card-sub (or period "Liberado · últimos 6 meses")]]]
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
    (->> series
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
  "Forecast chart: realized cash as bars, projected obligation as a line.
   The chart stays SVG-native so it remains lightweight and responsive."
  [data]
  (let [pts (trim-fluxo-series data)]
    (if (empty? pts)
      [chart-empty "Sem fluxo de caixa para o período"]
      (let [n   (count pts)
            vb-w 1000  vb-h 420
            lft 76   rgt 974   tp 44    btm 340
            lbl-y 382
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
            guide-nth (cond (> n 18) 3 (> n 10) 2 :else 1)

            today-i  (today-index pts)
            today-x  (when today-i (xf today-i))
            horizon-3-x (when today-i
                          (xf (min (dec n) (+ today-i 3))))

            proj-xy (->> pts
                         (map-indexed (fn [i p]
                                        (when-let [v (->num (:projetado p))]
                                          [(xf i) (yf v)])))
                         (keep identity)
                         vec)

            line-d (smooth-d proj-xy 0.35)

            area-d (when-let [p (smooth-d proj-xy 0.35)]
                     (str p " L " (first (peek proj-xy)) " " btm
                          " L " (ffirst proj-xy) " " btm " Z"))

            bar-w (max 10 (min 26 (* x-step 0.28)))]

        [:svg.chart.chart-fluxo
         {:viewBox (str "0 0 " vb-w " " vb-h)
        :preserveAspectRatio "none"
          :role "img"
          :aria-label "Fluxo de caixa mensal por competência"}
         [:desc "Barras mostram valores realizados e a apurar. Linha e área mostram valores projetados. O marcador vertical indica o mês atual quando visível."]

         [:defs
          [:linearGradient {:id "fluxo-realizado-fill" :x1 "0" :y1 "0" :x2 "0" :y2 "1"}
           [:stop {:offset "0%" :stop-color "var(--beige-light)"}]
           [:stop {:offset "100%" :stop-color "var(--beige-regular)"}]]
          [:linearGradient {:id "fluxo-a-apurar-fill" :x1 "0" :y1 "0" :x2 "0" :y2 "1"}
           [:stop {:offset "0%" :stop-color "var(--warning-light)"}]
           [:stop {:offset "100%" :stop-color "var(--warning-dark)"}]]
          [:linearGradient {:id "fluxo-projetado-fill" :x1 "0" :y1 "0" :x2 "0" :y2 "1"}
           [:stop {:offset "0%" :stop-color "var(--blue-light)" :stop-opacity 0.26}]
           [:stop {:offset "78%" :stop-color "var(--blue-light)" :stop-opacity 0.04}]
           [:stop {:offset "100%" :stop-color "var(--blue-light)" :stop-opacity 0}]]
          [:filter {:id "fluxo-tooltip-shadow" :x "-20%" :y "-20%" :width "140%" :height "150%"}
           [:feDropShadow {:dx 0 :dy 8 :stdDeviation 8 :flood-color "#000000" :flood-opacity 0.12}]]
          [:clipPath {:id "fluxo-plot-clip"}
           [:rect {:x lft :y tp :width cw :height ch :rx 8}]]]

         [:rect {:x lft :y tp :width cw :height ch :rx 8
                 :fill "var(--bg-1)"
                 :stroke "var(--border-subtle)"
                 :stroke-width 1
                 :vector-effect "non-scaling-stroke"}]

         (when (and today-x horizon-3-x)
           [:rect {:x today-x :y tp
                   :width (- horizon-3-x today-x)
                   :height ch
                   :fill "var(--beige-lightest)"
                   :fill-opacity 0.72
                   :clip-path "url(#fluxo-plot-clip)"}])

         [:g
          (for [[i _] (map-indexed vector pts)
                :when (zero? (mod i guide-nth))]
            ^{:key (str "vg" i)}
            [:line {:x1 (xf i) :y1 tp :x2 (xf i) :y2 btm
                    :stroke "var(--border-subtle)"
                    :stroke-width 1
                    :stroke-opacity 0.34
                    :vector-effect "non-scaling-stroke"}])]

         [:g
          (for [tv ticks]
            ^{:key (str "y" tv)}
            [:g
             [:line {:x1 lft :y1 (yf tv) :x2 rgt :y2 (yf tv)
                     :stroke "var(--border-subtle)" :stroke-width 1
                     :vector-effect "non-scaling-stroke"
                     :stroke-opacity (if (zero? tv) 0.9 0.68)
                     :stroke-dasharray (when (pos? tv) "3 6")}]
             [:text {:x (- lft 12) :y (+ (yf tv) 3.5) :text-anchor "end"
                     :font-family "IBM Plex Mono, monospace" :font-size 11
                     :fill "var(--fg-3)" :letter-spacing 0}
              (fmt-axis-val tv)]])]

         [:g {:clip-path "url(#fluxo-plot-clip)"}
          (for [[i p] (map-indexed vector pts)
                :let [rv (->num (:realizado p))]
                :when rv]
            ^{:key (str "b" i)}
            [:rect {:x (- (xf i) (/ bar-w 2)) :y (yf rv)
                    :width bar-w :height (max 2 (- btm (yf rv)))
                    :fill "url(#fluxo-realizado-fill)" :rx 4}])]

         [:g {:clip-path "url(#fluxo-plot-clip)"}
          (for [[i p] (map-indexed vector pts)
                :let [av (->num (:a_apurar p))]
                :when av]
            ^{:key (str "aa" i)}
            [:rect {:x (- (xf i) (/ bar-w 2)) :y (yf av)
                    :width bar-w :height (max 2 (- btm (yf av)))
                    :fill "url(#fluxo-a-apurar-fill)" :rx 4}])]

         (when area-d
           [:path {:d area-d
                   :fill "url(#fluxo-projetado-fill)"
                   :clip-path "url(#fluxo-plot-clip)"}])

         (when line-d
           [:path {:d line-d :fill "none" :stroke "var(--blue-regular)"
                   :stroke-width 2.6 :stroke-linecap "round"
                   :stroke-linejoin "round"
                   :clip-path "url(#fluxo-plot-clip)"
                   :vector-effect "non-scaling-stroke"}])

         [:g
          (for [[i p] (map-indexed vector pts)
                :let [proj-v (->num (:projetado p))
                      apurar-v (->num (:a_apurar p))
                      real-v (->num (:realizado p))
                      v (or proj-v apurar-v real-v)
                      proj? (some? proj-v)
                      apurar? (some? apurar-v)
                      kind (cond proj? "projetado" apurar? "a apurar" :else "realizado")
                      label (tooltip-label p kind v)
                      px (xf i)
                      py (yf v)
                      tip-w 176
                      tip-h 58
                      tip-x (cond
                              (> px (- vb-w 208)) (- px tip-w 14)
                              (< px (+ lft 80)) (+ px 14)
                              :else (- px (/ tip-w 2)))
                      tip-y (if (< py (+ tp 72)) (+ py 18) (- py tip-h 16))]
                :when v]
            ^{:key (str "d" i)}
            [:g.chart-point {:tabIndex 0 :role "img" :aria-label label}
             [:circle.chart-point-hit {:cx px :cy py :r 18}]
             [:path {:d (str "M " px " " py " h 0.01")
                     :fill "none"
                     :stroke (cond proj? "var(--blue-regular)"
                                   apurar? "var(--warning-dark)"
                                   :else "var(--beige-light)")
                     :stroke-width 6
                     :stroke-linecap "round"
                     :vector-effect "non-scaling-stroke"}]
             [:g.chart-tooltip
              [:rect {:x tip-x :y tip-y :width tip-w :height tip-h :rx 8
                      :filter "url(#fluxo-tooltip-shadow)"}]
              [:text {:x (+ tip-x 12) :y (+ tip-y 17)}
               (:label p)]
              [:text.kind {:x (+ tip-x 12) :y (+ tip-y 33)}
               kind]
              [:text.value {:x (+ tip-x 12) :y (+ tip-y 50)}
               (or (fmt/fmt-brl v) "R$ 0,00")]]])]

         (when today-x
           [:g
            [:line {:x1 today-x :y1 tp :x2 today-x :y2 btm
                    :stroke "var(--fg-1)" :stroke-width 1
                    :stroke-dasharray "3 4"
                    :stroke-opacity 0.45
                    :vector-effect "non-scaling-stroke"}]
            [:rect {:x (- today-x 32) :y (- tp 30)
                    :width 64 :height 20 :rx 10
                    :fill "var(--fg-1)"}]
            [:text {:x today-x :y (- tp 20)
                    :text-anchor "middle"
                    :dominant-baseline "central"
                    :font-family "IBM Plex Mono, monospace" :font-size 10
                    :font-weight 600 :fill "var(--bg-1)"
                    :letter-spacing 0}
             "mes atual"]])

         [:g {:font-family "IBM Plex Mono, monospace" :font-size 11
              :fill "var(--fg-3)" :text-anchor "middle" :letter-spacing 0}
          (for [[i p] (map-indexed vector pts)
                :when (zero? (mod i label-nth))]
            ^{:key (str "x" i)}
            [:text {:x (xf i) :y lbl-y} (:label p)])]]))))

(defn- horizon-col [{:keys [label value detail]}]
  [:div.col
   [:div.lab label]
   [:div.num (brl-value value "·")]
   (when detail [:div.meta detail])])

(defn- summary-col [{:keys [label value detail]}]
  [:div.col
   [:div.lab label]
   [:div.num (if (= :count (:kind value))
               (:text value)
               (brl-value value "·"))]
   (when detail [:div.meta detail])])

(defn- fluxo-caixa-card [{:keys [horizon period-summary filtered? series as-of]}]
  (let [has-realizado? (some #(->num (:realizado %)) series)
        has-a-apurar? (some #(->num (:a_apurar %)) series)
        projected-count (:apolices period-summary)]
    [:div.card.fluxo-card
     [:div.card-head
      [:div [:h3 "Fluxo de caixa mensal"]
       [:div.card-sub "Realizado, A apurar e Projetado por competência mensal"]]
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
                      :detail "com parcelas no filtro"}]]
       [:div.horizon-strip
        [horizon-col {:label "próximos 30d"
                      :value (:next_30 horizon)
                      :detail (when-let [n (:next_30_apolices horizon)]
                                (str n (if (= n 1) " apólice" " apólices")))}]
        [horizon-col {:label "próximos 60d"
                      :value (:next_60 horizon)
                      :detail (when-let [n (:next_60_apolices horizon)]
                                (str n (if (= n 1) " apólice" " apólices")))}]
        [horizon-col {:label "próximos 90d"
                      :value (:next_90 horizon)
                      :detail (when-let [n (:next_90_apolices horizon)]
                                (str n (if (= n 1) " apólice" " apólices")))}]])
     [:div.chart-frame
      [:div.chart-legend
       (when has-realizado?
         [:span.legend-dot {:style {:color "var(--beige-light)"}} "realizado"])
       (when has-a-apurar?
         [:span.legend-dot {:style {:color "var(--warning-dark)"}} "a apurar"])
       [:span.legend-line {:style {:color "var(--blue-regular)"}} "projetado"]
       (when-not filtered?
         [:span.legend-band "horizonte 90d"])]
      [chart-fluxo-caixa series]]]))

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
          period    @(rf/subscribe [:finance/period])
          user      @(rf/subscribe [:auth/current-user])
          route     @(rf/subscribe [:current-route-name])

          potencial    (or (:potencial_a_pagar dashboard) (:comissao_potencial dashboard))
          paga         (:comissao_paga dashboard)
          saldo-total  (:saldo_devedor_total dashboard)
          as-of        (format-asof (:as_of dashboard))
          period-tag   (period-suffix period)

          comm-ag        (:comissao_agenciamento dashboard)
          comissao-tot   (:comissao comm-ag)
          agenciam-tot   (:agenciamento comm-ag)
          comm-ag-series (or (:series comm-ag) [])
          comm-ag-period (:period comm-ag)

          fluxo-raw    (:fluxo_caixa dashboard)
          fluxo        (cond
                         (map? fluxo-raw) fluxo-raw
                         (sequential? fluxo-raw) {:series fluxo-raw}
                         :else {})
          fluxo-series (or (:series fluxo) [])
          period-summary (:period_summary fluxo)
          filtered? (or (not= :all (:year period))
                        (not= :all (:quarter period)))
          available-years (or (:available_years dashboard) [2024 2025 2026])
          future-year-floor (:future_year_floor dashboard)]
      [layout/page-shell
       {:current-route route
        :user user
        :crumbs ["plataforma rv" "finance" "dashboard"]
        :title "Visão financeira"
        :subtitle (when loading? "carregando…")
        :header-actions
        [[period-select {:year (:year period)
                         :quarter (:quarter period)
                         :years available-years
                         :future-year-floor future-year-floor}]]}

       ;; Row 1 — three KPIs
       [:div.kpi-grid.-three
        [kpi-potencial {:value potencial
                        :caption (str "a apurar + projetado · " period-tag)}]
        [kpi-paga      {:value paga
                        :caption (str "comissão + agenciamento · " period-tag)}]
        [kpi-saldo     {:value saldo-total
                        :caption "competências não realizadas · até 12 meses"}]]

       ;; Row 2 — Comissão x Agenciamento
       [comissao-agenciamento-card
        {:comissao comissao-tot
         :agenciamento agenciam-tot
         :series comm-ag-series
         :period comm-ag-period}]

       ;; Row 3 — Fluxo de Caixa Projetado
       [fluxo-caixa-card
        {:horizon (:horizon fluxo)
         :period-summary period-summary
         :filtered? filtered?
         :series fluxo-series
         :as-of as-of}]])))
