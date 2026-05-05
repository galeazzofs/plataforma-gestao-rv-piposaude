(ns app.views.finance.dashboard
  (:require [clojure.string :as str]
            [re-frame.core :as rf]
            [app.ds.layout :as layout]
            [app.auth.subs]
            [app.utils.format :as fmt]))

;; Finance dashboard — three editorial rows.
;; Row 1: Comissão Potencial · Comissão Paga · Saldo Devedor Total
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
  (cond
    (and (= :all year) (= :all quarter)) "histórico"
    (and (not= :all year) (= :all quarter)) (str year)
    (and (= :all year) (not= :all quarter)) (str "Q" quarter)
    :else (str "Q" quarter " · " year)))

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
;; Comissão Potencial = Σ commission.total_estimated across all policies in the
;;   policies index, including agenciamento.
;; Comissão Paga      = Σ policies.total_paid_comissao + total_paid_agenciamento.
;; Saldo Devedor      = projected obligation − paid, restricted to policies
;;   still inside their 12-month commission lifecycle.

(defn- kpi-potencial [{:keys [value caption]}]
  [:div.kpi
   [:div.kpi-label
    [layout/icon "target" {:width 14 :height 14}]
    "comissão potencial"]
   [:div.kpi-value (brl-value value "·")]
   [:div.kpi-foot
    [:span (or caption "todas as apólices · estimado")]]
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
    "saldo devedor · total"]
   [:div.kpi-value (brl-value value "·")]
   [:div.kpi-foot
    [:span (or caption "apólices em curso · até 12 meses")]]
   [:svg.kpi-grafismo {:style {:color "var(--neutral-light)"}}
    [:use {:href "#i-grafismo-listras"}]]])

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
    [chart-empty "Sem séries de comissão/agenciamento no período"]
    (let [pts (vec data)
          n   (count pts)
          slot (/ 540 (max 1 n))
          max-v (or (->> pts
                         (mapcat (fn [p] [(:comissao p) (:agenciamento p)]))
                         (filter some?) (reduce max 1))
                    1)
          y (fn [v] (- 220 (* (/ (or v 0) max-v) 180)))]
      [:svg.chart {:viewBox "0 0 600 240" :preserveAspectRatio "none"}
       [:g {:stroke "#E2E1DF" :stroke-width 1}
        [:line {:x1 40 :y1 40  :x2 600 :y2 40}]
        [:line {:x1 40 :y1 100 :x2 600 :y2 100}]
        [:line {:x1 40 :y1 160 :x2 600 :y2 160}]
        [:line {:x1 40 :y1 220 :x2 600 :y2 220}]]
       [:g
        (for [[i p] (map-indexed vector pts)
              :let [base (+ 80 (* i slot))]]
          ^{:key i}
          [:g
           (when (:comissao p)
             [:rect {:x base :y (y (:comissao p))
                     :width 18 :height (- 220 (y (:comissao p)))
                     :fill "#000" :rx 2}])
           (when (:agenciamento p)
             [:rect {:x (+ base 22) :y (y (:agenciamento p))
                     :width 18 :height (- 220 (y (:agenciamento p)))
                     :fill "#E6D9C2" :rx 2}])])]
       [:g {:font-family "Manrope" :font-size 11 :fill "#6B6663"}
        (for [[i p] (map-indexed vector pts)]
          ^{:key i}
          [:text {:x (+ 80 (* i slot)) :y 238} (:label p)])]])))

(defn- comissao-agenciamento-card [{:keys [comissao agenciamento series period as-of]}]
  (let [c (or (->num comissao) 0)
        a (or (->num agenciamento) 0)
        total (+ c a)
        com-pct (when (pos? total) (* 100 (/ c total)))
        ag-pct  (when (pos? total) (* 100 (/ a total)))]
    [:div.card
     [:div.card-head
      [:div [:h3 "Comissão x Agenciamento"]
       [:div.card-sub (or period "Liberado · últimos 6 meses")]]
      (when as-of [:span.card-asof (str "atualizado " as-of)])]
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

(defn- chart-fluxo-caixa [data]
  (if (empty? data)
    [chart-empty "Sem fluxo de caixa para o período"]
    (let [pts (vec data)
          n   (count pts)
          x-step (/ 540 (max 1 (dec n)))
          x  (fn [i] (+ 60 (* i x-step)))
          max-v (or (->> pts (mapcat (fn [p] [(:realizado p) (:projetado p)]))
                         (filter some?) (reduce max 1))
                    1)
          y  (fn [v] (- 220 (* (/ (or v 0) max-v) 180)))
          proj-pts (->> pts
                        (map-indexed (fn [i p]
                                       (when-let [v (or (:projetado p) (:realizado p))]
                                         (str (x i) " " (y v)))))
                        (filter some?))]
      [:svg.chart {:viewBox "0 0 600 240" :preserveAspectRatio "none"}
       [:g {:stroke "#E2E1DF" :stroke-width 1}
        [:line {:x1 40 :y1 40  :x2 600 :y2 40}]
        [:line {:x1 40 :y1 100 :x2 600 :y2 100}]
        [:line {:x1 40 :y1 160 :x2 600 :y2 160}]
        [:line {:x1 40 :y1 220 :x2 600 :y2 220}]]
       [:g {:fill "#E6D9C2"}
        (for [[i p] (map-indexed vector pts)
              :when (:realizado p)]
          ^{:key i}
          [:rect {:x (- (x i) 16) :y (y (:realizado p))
                  :width 32 :height (- 220 (y (:realizado p))) :rx 2}])]
       (when (seq proj-pts)
         [:path {:d (str "M " (str/join " L " proj-pts))
                 :fill "none" :stroke "#000" :stroke-width 2 :stroke-linecap "round"}])
       [:g {:fill "#000"}
        (for [[i p] (map-indexed vector pts)
              :when (or (:projetado p) (:realizado p))]
          ^{:key i}
          [:circle {:cx (x i) :cy (y (or (:projetado p) (:realizado p))) :r 3}])]
       [:g {:font-family "Manrope" :font-size 11 :fill "#6B6663"}
        (for [[i p] (map-indexed vector pts)]
          ^{:key i}
          [:text {:x (- (x i) 12) :y 238} (:label p)])]])))

(defn- horizon-col [{:keys [label value detail]}]
  [:div.col
   [:div.lab label]
   [:div.num (brl-value value "·")]
   (when detail [:div.meta detail])])

(defn- fluxo-caixa-card [{:keys [horizon series as-of]}]
  [:div.card
   [:div.card-head
    [:div [:h3 "Fluxo de caixa projetado"]
     [:div.card-sub "comissão + agenciamento · saídas previstas"]]
    [:div.legend
     [:span.legend-dot  {:style {:color "var(--beige-light)"}} "realizado"]
     [:span.legend-line {:style {:color "var(--black)"}} "projetado"]
     (when as-of [:span.card-asof (str "atualizado " as-of)])]]
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
                            (str n (if (= n 1) " apólice" " apólices")))}]]
   [chart-fluxo-caixa series]])

;; ----- Topbar period control ------------------------------------------

(defn- period-select
  "Two compact selects (year + quarter). Each defaults to \"Todos\"
   (all-time). Dispatches :finance/set-period on change."
  [{:keys [year quarter years]}]
  (let [on-change (fn [kind]
                    (fn [e]
                      (let [v (.. e -target -value)]
                        (rf/dispatch [:finance/set-period kind
                                      (if (= v "all") :all (js/parseInt v 10))]))))]
    [:div.period-control {:role "group" :aria-label "Filtro de período"}
     [:span.period-label "período"]
     [:select.period-select {:value (if (= year :all) "all" (str year))
                             :on-change (on-change :year)
                             :aria-label "Ano"}
      [:option {:value "all"} "Todos os anos"]
      (for [y (or years [])]
        ^{:key y} [:option {:value (str y)} (str y)])]
     [:select.period-select {:value (if (= quarter :all) "all" (str quarter))
                             :on-change (on-change :quarter)
                             :aria-label "Trimestre"}
      [:option {:value "all"} "Todos os trimestres"]
      [:option {:value "1"} "Q1"]
      [:option {:value "2"} "Q2"]
      [:option {:value "3"} "Q3"]
      [:option {:value "4"} "Q4"]]]))

(defn finance-dashboard-page []
  (rf/dispatch [:finance/fetch-dashboard])
  (fn []
    (let [dashboard @(rf/subscribe [:finance/dashboard])
          loading?  @(rf/subscribe [:finance/loading?])
          period    @(rf/subscribe [:finance/period])
          user      @(rf/subscribe [:auth/current-user])
          route     @(rf/subscribe [:current-route-name])

          potencial    (:comissao_potencial dashboard)
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
          available-years (or (:available_years dashboard) [2024 2025 2026])]
      [layout/page-shell
       {:current-route route
        :user user
        :crumbs ["plataforma rv" "finance" "dashboard"]
        :title "Visão financeira"
        :subtitle (when loading? "carregando…")
        :header-actions
        [[period-select {:year (:year period)
                         :quarter (:quarter period)
                         :years available-years}]]}

       ;; Row 1 — three KPIs
       [:div.kpi-grid.-three
        [kpi-potencial {:value potencial
                        :caption (str "todas as apólices · estimado · " period-tag)}]
        [kpi-paga      {:value paga
                        :caption (str "comissão + agenciamento · " period-tag)}]
        [kpi-saldo     {:value saldo-total
                        :caption "apólices em curso · até 12 meses"}]]

       ;; Row 2 — Comissão x Agenciamento
       [comissao-agenciamento-card
        {:comissao comissao-tot
         :agenciamento agenciam-tot
         :series comm-ag-series
         :period comm-ag-period
         :as-of as-of}]

       ;; Row 3 — Fluxo de Caixa Projetado
       [fluxo-caixa-card
        {:horizon (:horizon fluxo)
         :series fluxo-series
         :as-of as-of}]])))
