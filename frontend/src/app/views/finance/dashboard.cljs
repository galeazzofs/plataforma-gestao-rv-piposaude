(ns app.views.finance.dashboard
  (:require [clojure.string :as str]
            [re-frame.core :as rf]
            [app.ds.layout :as layout]
            [app.auth.subs]
            [app.utils.format :as fmt]))

;; Finance dashboard — design from "Visão financeira". Renders only data
;; returned by the API (re-frame subs); empty states stand in until the
;; backend has values to show.

(defn- pct-class [pct]
  (cond
    (>= (or pct 0) 100) "success"
    (>= (or pct 0) 70)  "warn"
    :else               "danger"))

(defn- bar [pct fill-class]
  [:div.bar
   [:div {:class (str "bar-fill " fill-class)
          :style {:width (str (min (or pct 0) 150) "%")}}]])

(defn- cell-progress [pct]
  [:div.cell-progress
   [bar pct (pct-class pct)]
   [:span.pct (str (.toFixed (or pct 0) 0) "%")]])

(defn- kpi
  [{:keys [icon label value foot grafismo grafismo-color]}]
  [:div.kpi
   [:div.kpi-label
    (when icon [layout/icon icon {:width 14 :height 14}])
    label]
   [:div.kpi-value value]
   (when foot [:div.kpi-foot foot])
   (when grafismo
     [:svg.kpi-grafismo {:style {:color grafismo-color}}
      [:use {:href (str "#i-" grafismo)}]])])

(defn- chart-empty [label]
  [:div {:style {:padding "32px" :text-align "center" :color "var(--fg-3)"
                 :font-family "var(--font-mono)" :font-size "12px"}}
   label])

(defn- chart-fluxo-caixa [data]
  (if (empty? data)
    [chart-empty "Sem fluxo de caixa para o período"]
    (let [pts (vec data)
          n   (count pts)
          x-step (/ 540 (max 1 (dec n)))
          x  (fn [i] (+ 60 (* i x-step)))
          max-v (or (->> pts (mapcat (fn [p] [(:realizado p) (:projetado p)])) (filter some?) (reduce max 1)) 1)
          y  (fn [v] (- 220 (* (/ (or v 0) max-v) 180)))
          proj-pts (->> pts (map-indexed (fn [i p] (when-let [v (or (:projetado p) (:realizado p))]
                                                     (str (x i) " " (y v))))) (filter some?))]
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

(defn- chart-orcado-realizado [data]
  (if (empty? data)
    [chart-empty "Sem orçado/realizado para o período"]
    (let [pts (vec data)
          n  (count pts)
          slot (/ 540 n)
          max-v (or (->> pts (mapcat (fn [p] [(:orcado p) (:realizado p)])) (filter some?) (reduce max 1)) 1)
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
           (when (:orcado p)
             [:rect {:x base :y (y (:orcado p)) :width 40 :height (- 220 (y (:orcado p)))
                     :fill "#BCBAB5" :rx 2 :opacity (if (:realizado p) 1 0.5)}])
           (when (:realizado p)
             [:rect {:x (+ base 45) :y (y (:realizado p)) :width 40 :height (- 220 (y (:realizado p)))
                     :fill "#000" :rx 2}])])]
       [:g {:font-family "Manrope" :font-size 11 :fill "#6B6663"}
        (for [[i p] (map-indexed vector pts)]
          ^{:key i}
          [:text {:x (+ 95 (* i slot)) :y 238} (:label p)])]])))

(defn- saldo-by-safra [years]
  (if (empty? years)
    [:div {:style {:padding "16px 0" :color "var(--fg-3)" :font-family "var(--font-mono)" :font-size "12px"}}
     "Sem saldo devedor para distribuir."]
    (let [items (vec years)
          max-v (or (->> items (map :amount) (filter some?) (reduce max 1)) 1)]
      [:div.dist
       (for [{:keys [year amount]} items]
         ^{:key year}
         [:div.dist-row
          [:div.dist-label (str year)]
          [:div.dist-bar
           [:div {:class (str "dist-bar-fill" (when (and (number? year) (< year 2026)) " beige"))
                  :style {:width (str (* 100 (/ (or amount 0) max-v)) "%")}}]]
          [:div.dist-amount (fmt/fmt-brl amount)]])])))

(defn- approvals-table [rows]
  [:div.card {:style {:padding 0 :overflow "hidden"}}
   [:div {:style {:padding "24px 24px 0"}}
    [:h3 "Aprovações pendentes"]
    [:div.card-sub "Apurações aprovadas pelo gerente, aguardando liberação financeira"]]
   [:table.table
    [:thead
     [:tr
      [:th "EV"]
      [:th "Período"]
      [:th.right "Comissão total"]
      [:th.center "Negócios"]
      [:th.center "Atingimento"]
      [:th "Status"]
      [:th.right "Ações"]]]
    [:tbody
     (if (empty? rows)
       [:tr [:td {:col-span 7 :style {:padding "48px 16px" :text-align "center" :color "var(--fg-3)"}}
             "Nenhuma apuração aguardando liberação"]]
       (for [row rows]
         ^{:key (or (:ev_id row) (:appraisal_id row))}
         [:tr
          [:td
           [:div.name (:ev_name row)]
           (when (:ev_id row) [:div.muted (str "id " (:ev_id row))])]
          [:td.num (or (:period row)
                       (when (and (:quarter row) (:year row))
                         (str "Q" (:quarter row) "/" (:year row)))
                       "·")]
          [:td.right.strong-num (or (fmt/fmt-brl (:commission_total row)) "·")]
          [:td.center.num (str (or (:deals row) (:policies_count row) "·"))]
          [:td [cell-progress (:achievement_pct row)]]
          [:td [:span.badge.badge-approved "Approved"]]
          [:td.right
           [:button.btn.btn-primary.btn-sm
            {:on-click #(rf/dispatch [:finance/liberar-pagamento (:appraisal_id row)])}
            "Liberar"]
           " "
           [:button.btn.btn-ghost.btn-sm
            {:on-click #(rf/dispatch [:finance/devolver (:appraisal_id row)])}
            "Devolver"]]]))]]])

(defn finance-dashboard-page []
  (rf/dispatch [:finance/fetch-dashboard])
  (fn []
    (let [dashboard @(rf/subscribe [:finance/dashboard])
          loading?  @(rf/subscribe [:finance/loading?])
          user      @(rf/subscribe [:auth/current-user])
          route     @(rf/subscribe [:current-route-name])
          saldo-total (:saldo_devedor_total dashboard)
          saldo-years (:saldo_by_year dashboard)
          fluxo-data  (:fluxo_caixa dashboard)
          orcado-data (:orcado_realizado dashboard)
          ev-summary  (or (:ev_summary dashboard) [])
          pending-rows (filter #(= (:appraisal_status %) "APPROVED") ev-summary)
          aguardando   (->> pending-rows (map :commission_total) (filter some?) (reduce + 0))
          released     (or (:liberado_mes dashboard) 0)
          orcado-pct   (:orcado_pct dashboard)
          orcado-delta (:saldo_delta_pct dashboard)
          released-delta (:liberado_delta_pct dashboard)]
      [layout/page-shell
       {:current-route route
        :user user
        :crumbs ["plataforma rv" "finance" "dashboard"]
        :title "Visão financeira"
        :subtitle (when loading? "carregando…")
        :header-actions
        [[:button.btn.btn-secondary
          {:on-click #(rf/dispatch [:finance/export])}
          [layout/icon "download" {:width 14 :height 14}] "Exportar"]
         [:button.btn.btn-primary
          {:on-click #(rf/dispatch [:navigate :finance/approval])}
          [layout/icon "check" {:width 14 :height 14}] "Liberar pagamentos"]]}

       ;; KPIs
       [:div.kpi-grid
        [kpi {:icon "money" :label "saldo devedor total"
              :value [:<> [:span.currency "R$"]
                      (or (fmt/int-brl saldo-total) "·")]
              :foot (when orcado-delta
                      [:<>
                       [:span {:class (str "delta " (if (neg? orcado-delta) "delta-down" "delta-up"))}
                        [layout/icon (if (neg? orcado-delta) "arrow-down" "arrow-up") {:width 12 :height 12}]
                        (str (.toFixed (Math/abs orcado-delta) 1) "%")]
                       " vs. trimestre anterior"])
              :grafismo "grafismo" :grafismo-color "var(--beige-light)"}]
        [kpi {:icon "clock" :label "aguardando aprovação"
              :value [:<> [:span.currency "R$"]
                      (or (fmt/int-brl aguardando) "0")]
              :foot [:span.badge.badge-pending
                     (str (count pending-rows) " apuraç" (if (= 1 (count pending-rows)) "ão" "ões"))]
              :grafismo "grafismo-listras" :grafismo-color "var(--warning-light)"}]
        [kpi {:icon "check" :label "liberado no mês"
              :value [:<> [:span.currency "R$"]
                      (or (fmt/int-brl released) "0")]
              :foot (when released-delta
                      [:<>
                       [:span {:class (str "delta " (if (neg? released-delta) "delta-down" "delta-up"))}
                        [layout/icon (if (neg? released-delta) "arrow-down" "arrow-up") {:width 12 :height 12}]
                        (str (.toFixed (Math/abs released-delta) 1) "%")]
                       " vs. mês anterior"])
              :grafismo "grafismo" :grafismo-color "var(--success-light)"}]
        [kpi {:icon "target" :label "orçado vs. realizado"
              :value (if orcado-pct
                       [:<> (.toFixed orcado-pct 1) [:span.frac "%"]]
                       "·")
              :foot (when orcado-pct
                      [bar orcado-pct (pct-class orcado-pct)])}]]

       ;; Charts
       [:div.two-col-eq
        [:div.card
         [:div.card-head
          [:div [:h3 "Fluxo de caixa projetado"]
           [:div.card-sub "Saídas previstas de comissão · próximos 6 meses"]]
          [:div.legend
           [:span.legend-line {:style {:color "var(--black)"}} "projetado"]
           [:span.legend-dot  {:style {:color "var(--beige-light)"}} "realizado"]]]
         [chart-fluxo-caixa fluxo-data]]
        [:div.card
         [:div.card-head
          [:div [:h3 "Orçado vs. realizado"]
           [:div.card-sub "Por trimestre · ano corrente"]]
          [:div.legend
           [:span.legend-dot {:style {:color "var(--neutral-regular)"}} "orçado"]
           [:span.legend-dot {:style {:color "var(--black)"}} "realizado"]]]
         [chart-orcado-realizado orcado-data]]]

       ;; Saldo by year
       [:div.card
        [:div.card-head
         [:div
          [:h3 "Saldo devedor por safra"]
          [:div.card-sub "Distribuição do passivo de comissões em aberto"]]]
        [saldo-by-safra saldo-years]]

       ;; Approvals — only the rows the API actually returned
       [approvals-table pending-rows]])))
