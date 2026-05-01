(ns app.views.finance.approval
  (:require [re-frame.core :as rf]
            [app.ds.layout :as layout]
            [app.auth.subs]))

;; Finance · Aprovação — design layout: filter chips + KPIs + approval table
;; with inline Liberar/Devolver actions, mirroring the finance dashboard's
;; "Aprovações pendentes" card style.

(defn- fmt-int [v]
  (when v (.toLocaleString (js/Math.round (if (string? v) (js/parseFloat v) v)) "pt-BR")))

(defn- pct-bar [pct fill-class]
  [:div.bar
   [:div {:class (str "bar-fill " fill-class)
          :style {:width (str (min (or pct 0) 150) "%")}}]])

(defn- pct-class [pct]
  (cond (>= (or pct 0) 100) "success" (>= (or pct 0) 70) "warn" :else "danger"))

(defn approval-page []
  (rf/dispatch [:finance/fetch-approval])
  (fn []
    (let [items    @(rf/subscribe [:finance/approval-items])
          loading? @(rf/subscribe [:finance/approval-loading?])
          user     @(rf/subscribe [:auth/current-user])
          route    @(rf/subscribe [:current-route-name])
          rows     (or items [])
          total-pending (->> rows (map :commission_total) (filter some?) (reduce + 0))]
      [layout/page-shell
       {:current-route route :user user
        :crumbs ["plataforma rv" "finance" "aprovação"]
        :title "Aprovação de Pagamentos"
        :subtitle (str (count rows) " apurações aguardando liberação")
        :header-actions
        [[:button.btn.btn-primary
          {:disabled (zero? (count rows))
           :on-click #(doseq [r rows]
                        (rf/dispatch [:finance/liberar-pagamento (:appraisal_id r)]))}
          [layout/icon "check" {:width 14 :height 14}] "Liberar todos"]]}

       ;; KPI — total a liberar (real, agregado)
       [:div.kpi-grid.-three
        [:div.kpi
         [:div.kpi-label [layout/icon "money" {:width 14 :height 14}] "total a liberar"]
         [:div.kpi-value [:span.currency "R$"] (or (fmt-int total-pending) "0")]
         [:div.kpi-foot (str (count rows) " apuraç" (if (= 1 (count rows)) "ão" "ões"))]]]

       ;; Approval table
       [:div.card {:style {:padding 0}}
        [:div {:style {:padding "24px 24px 16px"}}
         [:h3 "Apurações pendentes"]
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
          (cond
            loading?
            [:tr [:td {:col-span 7 :style {:padding "32px" :text-align "center" :color "var(--fg-3)"}}
                  "Carregando…"]]

            (empty? rows)
            [:tr [:td {:col-span 7 :style {:padding "48px" :text-align "center" :color "var(--fg-3)"}}
                  "Nenhuma apuração aguardando aprovação"]]

            :else
            (for [row rows]
              ^{:key (or (:appraisal_id row) (:id row))}
              [:tr
               [:td
                [:div.name (:ev_name row)]
                (when (:ev_id row) [:div.muted (str "id " (:ev_id row))])]
               [:td.num (str "Q" (:quarter row) "/" (:year row))]
               [:td.right.strong-num (str "R$ " (or (fmt-int (:commission_total row)) "—"))]
               [:td.center.num (str (or (:policies_count row) "—"))]
               [:td
                [:div.cell-progress
                 [pct-bar (:achievement_pct row) (pct-class (:achievement_pct row))]
                 [:span.pct (str (.toFixed (or (:achievement_pct row) 0) 0) "%")]]]
               [:td [:span.badge.badge-approved "Approved"]]
               [:td.right
                [:button.btn.btn-primary.btn-sm
                 {:on-click #(rf/dispatch [:finance/liberar-pagamento (:appraisal_id row)])}
                 "Liberar"]
                " "
                [:button.btn.btn-ghost.btn-sm
                 {:on-click #(rf/dispatch [:finance/devolver (:appraisal_id row)])}
                 "Devolver"]]]))]]]])))
