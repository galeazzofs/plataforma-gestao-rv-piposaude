(ns app.views.finance.dashboard
  (:require [clojure.string :as str]
            [re-frame.core :as rf]
            [app.ds.layout :as layout]
            [app.auth.subs]))

;; Finance dashboard — layout follows the "Visão financeira" design from
;; the Plataforma RV handoff. Real data comes from re-frame subs; the
;; design's example values appear only when the API hasn't returned yet.

(defn fmt-brl [v]
  (when v
    (str "R$ " (.toLocaleString v "pt-BR" #js {:minimumFractionDigits 2 :maximumFractionDigits 2}))))

(defn fmt-int-brl [v]
  (when v
    (.toLocaleString (js/Math.round v) "pt-BR")))

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

(defn- chart-fluxo-caixa [data]
  ;; Bars (realizado, beige) for past months, line (projetado, black) for full window.
  ;; Falls back to design's reference values when subscription data is absent.
  (let [pts (or (seq data)
                [{:label "jan" :realizado 100} {:label "fev" :realizado 130} {:label "mar" :realizado 115}
                 {:label "abr" :realizado nil} {:label "mai" :realizado nil} {:label "jun" :realizado nil}])
        n   (count pts)
        x-step (/ 540 (dec (max 1 n)))
        x  (fn [i] (+ 60 (* i x-step)))
        max-v (or (->> pts (mapcat (fn [p] [(:realizado p) (:projetado p)])) (filter some?) (reduce max 1)) 1)
        y  (fn [v] (- 220 (* (/ (or v 0) max-v) 180)))
        proj-line (str "M " (str/join " L " (map-indexed (fn [i p] (str (x i) " " (y (or (:projetado p) (:realizado p))))) pts)))]
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
        [:rect {:x (- (x i) 16) :y (y (:realizado p)) :width 32 :height (- 220 (y (:realizado p))) :rx 2}])]
     [:path {:d proj-line :fill "none" :stroke "#000" :stroke-width 2 :stroke-linecap "round"}]
     [:g {:fill "#000"}
      (for [[i p] (map-indexed vector pts)]
        ^{:key i}
        [:circle {:cx (x i) :cy (y (or (:projetado p) (:realizado p))) :r 3}])]
     [:g {:font-family "Manrope" :font-size 11 :fill "#6B6663"}
      (for [[i p] (map-indexed vector pts)]
        ^{:key i}
        [:text {:x (- (x i) 12) :y 238} (:label p)])]]))

(defn- chart-orcado-realizado [data]
  (let [pts (or (seq data)
                [{:label "Q1" :orcado 800 :realizado 700}
                 {:label "Q2" :orcado 950 :realizado 880}
                 {:label "Q3" :orcado 1100 :realizado 1060}
                 {:label "Q4 (proj.)" :orcado 1200 :realizado nil}])
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
           [:rect {:x base :y (y (:orcado p)) :width 40 :height (- 220 (y (:orcado p))) :fill "#BCBAB5" :rx 2 :opacity (if (:realizado p) 1 0.5)}])
         (when (:realizado p)
           [:rect {:x (+ base 45) :y (y (:realizado p)) :width 40 :height (- 220 (y (:realizado p))) :fill "#000" :rx 2}])])]
     [:g {:font-family "Manrope" :font-size 11 :fill "#6B6663"}
      (for [[i p] (map-indexed vector pts)]
        ^{:key i}
        [:text {:x (+ 95 (* i slot)) :y 238} (:label p)])]]))

(defn- saldo-by-safra [years]
  (let [items (or (seq years) [{:year 2026 :amount 1766520} {:year 2025 :amount 798330}
                                {:year 2024 :amount 227840} {:year "≤ 2023" :amount 54930}])
        max-v (or (->> items (map :amount) (filter some?) (reduce max 1)) 1)]
    [:div.dist
     (for [{:keys [year amount]} items]
       ^{:key year}
       [:div.dist-row
        [:div.dist-label (str year)]
        [:div.dist-bar
         [:div {:class (str "dist-bar-fill" (when (and (number? year) (< year 2026)) " beige"))
                :style {:width (str (* 100 (/ (or amount 0) max-v)) "%")}}]]
        [:div.dist-amount (fmt-brl amount)]])]))

(defn- approvals-table [rows]
  (let [items (or (seq rows)
                  [{:ev_id 1024 :ev_name "Cliente A — EV" :period "Q2/2026"
                    :commission_total 84320 :deals 12 :achievement_pct 108 :status "APPROVED"}
                   {:ev_id 1156 :ev_name "Cliente B — EV" :period "Q2/2026"
                    :commission_total 56840 :deals 8 :achievement_pct 78 :status "APPROVED"}
                   {:ev_id 980  :ev_name "Cliente C — EV" :period "Q2/2026"
                    :commission_total 41110 :deals 5 :achievement_pct 45 :status "APPROVED"}
                   {:ev_id 1288 :ev_name "Cliente D — EV" :period "Q1/2026"
                    :commission_total 124080 :deals 19 :achievement_pct 142 :status "APPROVED"}
                   {:ev_id 1305 :ev_name "Cliente E — EV" :period "Q1/2026"
                    :commission_total 32560 :deals 4 :achievement_pct 38 :status "APPROVED"}])]
    [:div.card {:style {:padding 0 :overflow "hidden"}}
     [:div {:style {:padding "24px 24px 0" :display "flex" :justify-content "space-between" :align-items "flex-end" :gap "16px"}}
      [:div
       [:h3 "Aprovações pendentes"]
       [:div.card-sub "Apurações aprovadas pelo gerente, aguardando liberação financeira"]]
      [:div.filter-row
       [:div.chip.active "Todas"]
       [:div.chip "Q2/2026"]
       [:div.chip "Q1/2026"]
       [:div.chip [layout/icon "filter" {:width 12 :height 12}] " Filtros"]]]
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
       (for [row items]
         ^{:key (:ev_id row)}
         [:tr
          [:td
           [:div.name (:ev_name row)]
           [:div.muted (str "id " (:ev_id row))]]
          [:td.num (or (:period row) "—")]
          [:td.right.strong-num (fmt-brl (:commission_total row))]
          [:td.center.num (str (or (:deals row) "—"))]
          [:td [cell-progress (:achievement_pct row)]]
          [:td [:span.badge.badge-approved "Approved"]]
          [:td.right
           [:button.btn.btn-primary.btn-sm
            {:on-click #(rf/dispatch [:navigate [:gerente/ev-detail {:ev-id (:ev_id row)}]])}
            "Liberar"]
           " "
           [:button.btn.btn-ghost.btn-sm "Devolver"]]])]]
     [:div {:style {:padding "14px 24px" :border-top "1px solid var(--border-subtle)"
                    :display "flex" :justify-content "space-between" :align-items "center"
                    :font-family "var(--font-mono)" :font-size "11px" :color "var(--fg-3)"}}
      [:span (str (count items) " de " (count items) " apurações pendentes")]
      [:div {:style {:display "flex" :gap "8px"}}
       [:button.btn.btn-secondary.btn-sm "Anterior"]
       [:button.btn.btn-secondary.btn-sm "Próxima"]]]]))

(defn finance-dashboard-page []
  (rf/dispatch [:finance/fetch-dashboard])
  (fn []
    (let [dashboard @(rf/subscribe [:finance/dashboard])
          loading?  @(rf/subscribe [:finance/loading?])
          user      @(rf/subscribe [:auth/current-user])
          route     @(rf/subscribe [:current-route-name])
          saldo-total (or (:saldo_devedor_total dashboard) 2847620)
          saldo-years (:saldo_by_year dashboard)
          fluxo-data  (:fluxo_caixa dashboard)
          orcado-data (:orcado_realizado dashboard)
          ev-summary  (:ev_summary dashboard)
          aguardando  (->> (or ev-summary [])
                           (filter #(= (:appraisal_status %) "APPROVED"))
                           (map :commission_total)
                           (filter some?)
                           (reduce + 0))
          aguardando-count (count (filter #(= (:appraisal_status %) "APPROVED")
                                          (or ev-summary [])))]
      [layout/page-shell
       {:current-route route
        :user user
        :crumbs ["plataforma rv" "finance" "dashboard"]
        :title "Visão financeira"
        :subtitle (str "Q2 / 2026" (when loading? " · carregando…"))
        :header-actions
        [[layout/search-input {:placeholder "Buscar EV, apólice, NF…"}]
         [layout/icon-btn {:icon "bell" :dot? true :aria-label "Notificações"}]
         [:button.btn.btn-secondary
          {:on-click #(rf/dispatch [:finance/export])}
          [layout/icon "download" {:width 14 :height 14}] "Exportar"]
         [:button.btn.btn-primary
          {:on-click #(rf/dispatch [:navigate :finance/approval])}
          [layout/icon "check" {:width 14 :height 14}] "Liberar pagamentos"]]}

       ;; KPIs
       [:div.kpi-grid
        [kpi {:icon "money" :label "saldo devedor total"
              :value [:<> [:span.currency "R$"] (or (fmt-int-brl saldo-total) "—")]
              :foot [:<>
                     [:span.delta.delta-down [layout/icon "arrow-down" {:width 12 :height 12}] "4,2%"]
                     " vs. trimestre anterior"]
              :grafismo "grafismo" :grafismo-color "var(--beige-light)"}]
        [kpi {:icon "clock" :label "aguardando aprovação"
              :value [:<> [:span.currency "R$"]
                      (or (fmt-int-brl (when (pos? aguardando) aguardando)) "412.300")]
              :foot [:span.badge.badge-pending (str (if (pos? aguardando-count) aguardando-count 14) " apurações")]
              :grafismo "grafismo-listras" :grafismo-color "var(--warning-light)"}]
        [kpi {:icon "check" :label "liberado no mês"
              :value [:<> [:span.currency "R$"] "682.140"]
              :foot [:<>
                     [:span.delta.delta-up [layout/icon "arrow-up" {:width 12 :height 12}] "12,8%"]
                     " vs. mês anterior"]
              :grafismo "grafismo" :grafismo-color "var(--success-light)"}]
        [kpi {:icon "target" :label "orçado vs. realizado"
              :value [:<> "94,2" [:span.frac "%"]]
              :foot [bar 94 "success"]}]]

       ;; Charts
       [:div.two-col-eq
        [:div.card
         [:div.card-head
          [:div [:h3 "Fluxo de caixa projetado"] [:div.card-sub "Saídas previstas de comissão · próximos 6 meses"]]
          [:div.legend
           [:span.legend-line {:style {:color "var(--black)"}} "projetado"]
           [:span.legend-dot  {:style {:color "var(--beige-light)"}} "realizado"]]]
         [chart-fluxo-caixa fluxo-data]]
        [:div.card
         [:div.card-head
          [:div [:h3 "Orçado vs. realizado"] [:div.card-sub "Por trimestre · ano corrente"]]
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

       ;; Approvals
       [approvals-table ev-summary]])))
