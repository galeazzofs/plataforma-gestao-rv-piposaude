(ns app.views.revops.dashboard
  (:require [re-frame.core :as rf]
            [app.ds.layout :as layout]
            [app.ds.nav :as nav]
            [app.utils.format :as fmt]
            [app.auth.subs]))

;; Re-exported for legacy callers in other revops views that still reference
;; `revops-shell/sidebar-items`.
(def sidebar-items nav/admin-items)

;; Admin / RevOps dashboard. Renders only data from re-frame subs; empty
;; states stand in until the API has values.

(defn- status->badge [status]
  (case status
    "REVIEWING"   [:span.badge.badge-review "Reviewing"]
    "VALIDATING"  [:span.badge.badge-validating "Validating"]
    "LOCKED"      [:span.badge.badge-locked "Locked"]
    "DRAFT"       [:span.badge.badge-draft "Draft"]
    "APPROVED"    [:span.badge.badge-approved "Approved"]
    "CALCULATING" [:span.badge.badge-calc "Calculating"]
    [:span.badge.badge-locked (or status "·")]))

(def ^:private steps ["DRAFT" "CALCULATING" "REVIEWING" "VALIDATING" "APPROVED" "LOCKED"])

(defn- step-of [status]
  (let [idx (.indexOf (clj->js steps) (or status "DRAFT"))]
    (when (>= idx 0) (inc idx))))

(defn- appraisal-row [{:keys [a]}]
  [:tr
   [:td.name.num (str "Q" (:quarter a) "/" (:year a))]
   [:td [status->badge (:status a)]]
   [:td.center.num (str (or (:ev_count a) "·"))]
   [:td.right.strong-num (or (fmt/fmt-brl-int (:total_amount a)) "·")]
   [:td.right
    (case (:status a)
      "REVIEWING"  [:button.btn.btn-primary.btn-sm
                    {:on-click #(rf/dispatch [:navigate [:revops/appraisal-review {:id (:id a)}]])}
                    "Revisar"]
      "VALIDATING" [:button.btn.btn-secondary.btn-sm
                    {:on-click #(rf/dispatch [:navigate [:revops/appraisal-review {:id (:id a)}]])}
                    "Acompanhar"]
      [:button.btn.btn-ghost.btn-sm
       {:on-click #(rf/dispatch [:navigate [:revops/appraisal-review {:id (:id a)}]])}
       "Ver"])]])

(defn- describe-audit [{:keys [action table_name row_id]}]
  (let [a (case action
            "INSERT" "criou"
            "UPDATE" "atualizou"
            "DELETE" "removeu"
            (or action "alterou"))]
    (str a " " (or table_name "registro")
         (when row_id (str " · #" row_id)))))

(defn- audit-icon [{:keys [action table_name]}]
  (cond
    (= table_name "appraisals") "cog"
    (= table_name "policies")   "doc"
    (= table_name "users")      "users"
    (= table_name "settings")   "cog"
    (= action "INSERT")         "plus"
    (= action "DELETE")         "alert"
    :else                       "edit"))

(defn revops-dashboard-page []
  (rf/dispatch [:revops/fetch-appraisals])
  (rf/dispatch [:revops/fetch-sync-status])
  (rf/dispatch [:revops/fetch-contestations])
  (rf/dispatch [:revops/fetch-audit-log {:page 1}])
  (fn []
    (let [appraisals    @(rf/subscribe [:revops/appraisals])
          sync-status   @(rf/subscribe [:revops/sync-status])
          contestations @(rf/subscribe [:revops/contestations])
          audit-log     @(rf/subscribe [:revops/audit-log])
          user          @(rf/subscribe [:auth/current-user])
          route         @(rf/subscribe [:current-route-name])
          active        (first (filter #(not= (:status %) "LOCKED") (or appraisals [])))
          contest-open  (count (filter #(= (:status %) "CONTESTED") (or contestations [])))
          recent        (->> (or appraisals [])
                             (sort-by (juxt :year :quarter) #(compare %2 %1))
                             (take 4))
          recent-events (->> (or (:items audit-log) []) (take 5))
          synced        (:records_synced sync-status)]
      [layout/page-shell
       {:current-route route :user user
        :crumbs ["plataforma rv" "admin" "dashboard"]
        :title "Painel admin"
        :subtitle "Visão geral do ciclo de comissões"
        :header-actions
        [[:button.btn.btn-primary
          {:on-click #(rf/dispatch [:navigate :revops/appraisal])}
          [layout/icon "plus" {:width 14 :height 14}] "Nova apuração"]]}

       ;; KPIs (3-up)
       [:div.kpi-grid.-three
        [:div.kpi
         [:div.kpi-label [layout/icon "cog" {:width 14 :height 14}] "apuração ativa"]
         [:div.kpi-value
          (if active
            [:<> "Q" (:quarter active) [:span.frac (str "/" (mod (or (:year active) 0) 100))]]
            "·")]
         [:div.kpi-foot
          (when active [status->badge (:status active)])
          (when-let [n (some-> active :status step-of)]
            [:span (str "etapa " n " de " (count steps))])]
         [:svg.kpi-grafismo {:style {:color "var(--blue-light)"}} [:use {:href "#i-grafismo"}]]]
        [:div.kpi
         [:div.kpi-label [layout/icon "alert" {:width 14 :height 14}] "contestações abertas"]
         [:div.kpi-value (str contest-open)]
         [:div.kpi-foot
          (if (pos? contest-open)
            [:button.btn.btn-ghost.btn-sm
             {:style {:padding 0}
              :on-click #(rf/dispatch [:navigate :revops/contestations])}
             "Ver pendentes " [layout/icon "arrow-right" {:width 12 :height 12}]]
            [:span "Sem pendências"])]
         [:svg.kpi-grafismo {:style {:color "var(--warning-light)"}} [:use {:href "#i-grafismo-listras"}]]]
        [:div.kpi
         [:div.kpi-label [layout/icon "refresh" {:width 14 :height 14}] "último sync hubspot"]
         [:div.kpi-value {:style {:font-size "30px"}}
          (or (:last_sync sync-status) "·")]
         [:div.kpi-foot
          (when (:status sync-status)
            [:span {:class (str "badge badge-" (case (:status sync-status)
                                                 "OK" "approved"
                                                 "RUNNING" "review"
                                                 "error"))}
             (:status sync-status)])
          (when synced
            [:span (str (.toLocaleString synced "pt-BR") " negócios sincronizados")])]]]

       ;; Callout when an appraisal is in review
       (when (and active (= (:status active) "REVIEWING"))
         [:div.callout
          [layout/icon "info" {:width 20 :height 20}]
          [:div {:style {:flex 1}}
           [:strong (str "Apuração Q" (:quarter active) "/" (:year active) " está em revisão")]
           [:p {:style {:font-size "13px" :color "var(--fg-3)" :margin-top "2px"}}
            "Os cálculos foram concluídos. RevOps precisa validar os valores antes de enviar para os EVs."]]
          [:button.btn.btn-primary.btn-sm
           {:on-click #(rf/dispatch [:navigate [:revops/appraisal-review {:id (:id active)}]])}
           "Revisar valores " [layout/icon "arrow-right" {:width 12 :height 12}]]])

       ;; Two col: recent appraisals + recent activity from audit log
       [:div.two-col
        [:div.card {:style {:padding 0}}
         [:div {:style {:padding "24px 24px 16px" :display "flex" :justify-content "space-between" :align-items "center"}}
          [:div [:h3 "Apurações recentes"]
           [:div.card-sub
            (str (count recent) " ciclo" (when (not= 1 (count recent)) "s"))]]
          [:button.btn.btn-ghost.btn-sm
           {:on-click #(rf/dispatch [:navigate :revops/appraisal])}
           "Ver todas " [layout/icon "arrow-right" {:width 12 :height 12}]]]
         [:table.table
          [:thead
           [:tr
            [:th "Período"] [:th "Status"]
            [:th.center "EVs"] [:th.right "Total"] [:th.right "Ações"]]]
          [:tbody
           (if (empty? recent)
             [:tr [:td {:col-span 5 :style {:padding "32px" :text-align "center" :color "var(--fg-3)"}}
                   "Nenhuma apuração criada"]]
             (for [a recent]
               ^{:key (:id a)} [appraisal-row {:a a}]))]]]

        [:div.card
         [:div.card-head
          [:div [:h3 "Atividade recente"] [:div.card-sub "Últimos eventos do sistema"]]
          [:button.btn.btn-ghost.btn-sm
           {:on-click #(rf/dispatch [:navigate :revops/audit-log])}
           "Audit log " [layout/icon "arrow-right" {:width 12 :height 12}]]]
         (if (empty? recent-events)
           [:div {:style {:padding "16px 0" :color "var(--fg-3)" :font-family "var(--font-mono)" :font-size "12px"}}
            "Sem atividade recente."]
           [:div.activity
            (for [e recent-events]
              ^{:key (:id e)}
              [:div.activity-item
               [:div.activity-dot
                [layout/icon (audit-icon e) {:width 11 :height 11}]]
               [:div.activity-content
                [:strong (or (:description e) (describe-audit e))]
                [:span.when (str (or (:user_name e) (:user_email e) "sistema")
                                 (when (:created_at e) (str " · " (:created_at e))))]]])])]]])))
