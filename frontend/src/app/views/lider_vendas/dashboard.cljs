(ns app.views.lider-vendas.dashboard
  (:require [re-frame.core :as rf]
            [app.ds.layout :as layout]
            [app.auth.subs]))

(defn- num [v]
  (cond
    (nil? v) 0
    (number? v) v
    (string? v) (or (js/parseFloat v) 0)
    :else 0))

(defn- fmt-int [v]
  (when v (.toLocaleString (js/Math.round (num v)) "pt-BR")))

(defn- pct-bar [pct fill-class]
  [:div.bar
   [:div {:class (str "bar-fill " fill-class)
          :style {:width (str (min (num pct) 150) "%")}}]])

(defn- pct-class [pct]
  (let [value (num pct)]
    (cond (>= value 100) "success" (>= value 70) "warn" :else "danger")))

(defn- status-badge [status]
  (case status
    "VALIDATING" [:span.badge.badge-review "Validar"]
    "LIDER_REVIEW" [:span.badge.badge-review "Aprovado"]
    "REVOPS_REVIEW" [:span.badge.badge-pending "RevOps"]
    "LOCKED" [:span.badge.badge-locked "Fechado"]
    [:span.badge.badge-locked (or status "Sem ciclo")]))

(defn- leadership-row [row]
  (let [status (:status row)
        validating? (= status "VALIDATING")]
    [:tr
     [:td.name.num (str "Q" (:quarter row) "/" (:year row))]
     [:td.right.strong-num (str "R$ " (or (fmt-int (:bonus_amount row)) "0"))]
     [:td.right.num (str (or (some-> (:pct_mrr row) num (* 100) (.toFixed 0)) "0") "%")]
     [:td.right.num (str (or (some-> (:pct_sql row) num (* 100) (.toFixed 0)) "0") "%")]
     [:td [status-badge status]]
     [:td.right
      (if validating?
        [:button.btn.btn-primary.btn-sm
         {:on-click #(rf/dispatch [:lider-vendas/approve-appraisal (:id row)])}
         [layout/icon "check" {:width 14 :height 14}] "Aprovar"]
        [:span.muted "Sem acao"])]]))

(defn- ev-row [{:keys [id name achievement_pct mrr commission appraisal_status deals_count]}]
  (let [pct (num achievement_pct)]
    [:tr
     [:td
      [:div.name name]
      [:div.muted (str "id " (or id "-"))]]
     [:td.center.num (str (or deals_count 0))]
     [:td.right.strong-num (str "R$ " (or (fmt-int mrr) "0"))]
     [:td
      [:div.cell-progress
       [pct-bar pct (pct-class pct)]
       [:span.pct (str (.toFixed pct 0) "%")]]]
     [:td.right.strong-num (str "R$ " (or (fmt-int commission) "0"))]
     [:td [status-badge appraisal_status]]
     [:td.right
      [:button.btn.btn-ghost.btn-sm
       {:on-click #(rf/dispatch [:navigate [:lider-vendas/ev-detail {:ev-id id}]])}
       "Ver"]]]))

(defn lider-vendas-dashboard-page []
  (rf/dispatch [:lider-vendas/fetch-team])
  (rf/dispatch [:lider-vendas/fetch-appraisals])
  (fn []
    (let [members    @(rf/subscribe [:lider-vendas/team-members])
          appraisals @(rf/subscribe [:lider-vendas/appraisals])
          user       @(rf/subscribe [:auth/current-user])
          route      @(rf/subscribe [:current-route-name])
          rows       (or members [])
          approvals  (or appraisals [])
          pending    (filter #(= (:status %) "VALIDATING") approvals)
          total-commission (->> rows (map #(num (:commission %))) (reduce + 0))
          pct-values (->> rows (map :achievement_pct) (filter some?) (map num))
          avg-pct    (if (seq pct-values)
                       (/ (reduce + 0 pct-values) (count pct-values))
                       0)
          pending-count (count pending)
          active-count (count rows)]
      [layout/page-shell
       {:current-route route :user user
        :crumbs ["plataforma rv" "lider de vendas" "dashboard"]
        :title "Painel do Lider de Vendas"
        :subtitle (str active-count " EVs no time")
        :header-actions nil}

       [:div.kpi-grid
        [:div.kpi
         [:div.kpi-label [layout/icon "team" {:width 14 :height 14}] "EVs no time"]
         [:div.kpi-value (str active-count)]
         [:div.kpi-foot "ativos na carteira"]]
        [:div.kpi
         [:div.kpi-label [layout/icon "target" {:width 14 :height 14}] "atingimento medio"]
         [:div.kpi-value (str (.toFixed avg-pct 0)) [:span.frac "%"]]
         [:div.kpi-foot [pct-bar avg-pct (pct-class avg-pct)]]]
        [:div.kpi
         [:div.kpi-label [layout/icon "money" {:width 14 :height 14}] "comissao time"]
         [:div.kpi-value [:span.currency "R$"] (fmt-int total-commission)]]
        [:div.kpi
         [:div.kpi-label [layout/icon "alert" {:width 14 :height 14}] "minhas aprovacoes"]
         [:div.kpi-value (str pending-count)]
         [:div.kpi-foot (when (pos? pending-count) "aguardando sua acao")]]]

       (when (seq approvals)
         [:div.card {:style {:padding 0}}
          [:div {:style {:padding "18px 20px 0"}}
           [:h3 "Minhas apuracoes de lideranca"]
           [:div.card-sub "Bonus trimestral e status da validacao do lider"]]
          [:table.table
           [:thead
            [:tr
             [:th "Periodo"]
             [:th.right "Bonus"]
             [:th.right "% MRR"]
             [:th.right "% SQL"]
             [:th "Status"]
             [:th.right "Acoes"]]]
           [:tbody
            (for [row approvals]
              ^{:key (:id row)}
              [leadership-row row])]]])

       [:div.card {:style {:padding 0}}
        [:div {:style {:padding "18px 20px 12px"}}
         [:h3 "EVs do time"]
         [:div.card-sub "Comissoes calculadas na ultima apuracao mensal"]]
        [:table.table
         [:thead
          [:tr
           [:th "EV"]
           [:th.center "Negocios"]
           [:th.right "MRR vendido"]
           [:th "Atingimento"]
           [:th.right "Comissao"]
           [:th "Status"]
           [:th.right "Acoes"]]]
         [:tbody
          (if (empty? rows)
            [:tr [:td {:col-span 7 :style {:padding "48px" :text-align "center" :color "var(--fg-3)"}}
                  "Nenhum EV no time"]]
            (for [row rows] ^{:key (:id row)} [ev-row row]))]]]])))
