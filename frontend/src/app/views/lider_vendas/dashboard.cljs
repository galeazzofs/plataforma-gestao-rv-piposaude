(ns app.views.lider-vendas.dashboard
  (:require [re-frame.core :as rf]
            [app.ds.layout :as layout]
            [app.auth.subs]))

(defn- fmt-int [v]
  (when v (.toLocaleString (js/Math.round (if (string? v) (js/parseFloat v) v)) "pt-BR")))

(defn- pct-bar [pct fill-class]
  [:div.bar
   [:div {:class (str "bar-fill " fill-class)
          :style {:width (str (min (or pct 0) 150) "%")}}]])

(defn- ev-row [{:keys [id name achievement_pct mrr commission appraisal_status]}]
  (let [pct (or achievement_pct 0)
        fill (cond (>= pct 100) "success" (>= pct 70) "warn" :else "danger")]
    [:tr
     [:td
      [:div.name name]
      [:div.muted (str "id " (or id "·"))]]
     [:td.center.num (str (or (:deals_count {}) "·"))]
     [:td.right.strong-num (str "R$ " (or (fmt-int mrr) "·"))]
     [:td
      [:div.cell-progress
       [pct-bar pct fill]
       [:span.pct (str (.toFixed pct 0) "%")]]]
     [:td.right.strong-num (str "R$ " (or (fmt-int commission) "·"))]
     [:td (case appraisal_status
            "APPROVED"  [:span.badge.badge-approved "Aprovado"]
            "REVIEWING" [:span.badge.badge-review "Revisar"]
            "LOCKED"    [:span.badge.badge-locked "Férias"]
            [:span.badge.badge-locked (or appraisal_status "·")])]
     [:td.right
      (if (= appraisal_status "REVIEWING")
        [:button.btn.btn-primary.btn-sm
         {:on-click #(rf/dispatch [:navigate [:lider-vendas/ev-detail {:ev-id id}]])}
         "Aprovar"]
        [:button.btn.btn-ghost.btn-sm
         {:on-click #(rf/dispatch [:navigate [:lider-vendas/ev-detail {:ev-id id}]])}
         "Ver"])]]))

(defn lider-vendas-dashboard-page []
  (rf/dispatch [:lider-vendas/fetch-team])
  (fn []
    (let [members  @(rf/subscribe [:lider-vendas/team-members])
          user     @(rf/subscribe [:auth/current-user])
          route    @(rf/subscribe [:current-route-name])
          rows     (or members [])
          total-commission (->> rows (map :commission) (filter some?) (reduce + 0))
          avg-pct (if (empty? rows) 0
                      (->> rows (map :achievement_pct) (filter some?)
                           ((fn [vs] (when (seq vs) (/ (reduce + 0 vs) (count vs)))))))
          pending-approvals (count (filter #(= (:appraisal_status %) "REVIEWING") rows))
          actives (count (filter #(not= (:appraisal_status %) "LOCKED") rows))
          on-leave (count (filter #(= (:appraisal_status %) "LOCKED") rows))]
      [layout/page-shell
       {:current-route route :user user
        :crumbs ["plataforma rv" "líder de vendas" "dashboard"]
        :title "Painel do Líder de Vendas"
        :subtitle "Time de Vendas · Q2/2026"
        :header-actions nil}

       ;; KPIs
       [:div.kpi-grid
        [:div.kpi
         [:div.kpi-label [layout/icon "team" {:width 14 :height 14}] "EVs no time"]
         [:div.kpi-value (str (count rows))]
         [:div.kpi-foot (str actives " ativos · " on-leave " férias")]]
        [:div.kpi
         [:div.kpi-label [layout/icon "target" {:width 14 :height 14}] "atingimento médio"]
         [:div.kpi-value (str (.toFixed (or avg-pct 0) 0)) [:span.frac "%"]]
         [:div.kpi-foot
          [pct-bar avg-pct
           (cond (>= (or avg-pct 0) 100) "success" (>= (or avg-pct 0) 70) "warn" :else "danger")]]]
        [:div.kpi
         [:div.kpi-label [layout/icon "money" {:width 14 :height 14}] "comissão total time"]
         [:div.kpi-value [:span.currency "R$"] (fmt-int total-commission)]]
        [:div.kpi
         [:div.kpi-label [layout/icon "alert" {:width 14 :height 14}] "aprovações pendentes"]
         [:div.kpi-value (str pending-approvals)]
         [:div.kpi-foot
          (when (pos? pending-approvals) "aguardando sua aprovação")]]]

       ;; Team table
       [:div.card {:style {:padding 0}}
        [:div {:style {:padding "18px 20px 12px"}}
         [:h3 "EVs do time"]
         [:div.card-sub "Ranking por atingimento"]]
        [:table.table
         [:thead
          [:tr
           [:th "EV"]
           [:th.center "Negócios"]
           [:th.right "MRR vendido"]
           [:th "Atingimento"]
           [:th.right "Comissão"]
           [:th "Status"]
           [:th.right "Ações"]]]
         [:tbody
          (if (empty? rows)
            [:tr [:td {:col-span 7 :style {:padding "48px" :text-align "center" :color "var(--fg-3)"}}
                  "Nenhum EV no time"]]
            (for [row rows] ^{:key (:id row)} [ev-row row]))]]]])))
