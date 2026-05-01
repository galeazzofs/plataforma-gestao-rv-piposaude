(ns app.views.revops.dashboard
  (:require [re-frame.core :as rf]
            [app.ds.layout :as layout]
            [app.ds.nav :as nav]
            [app.auth.subs]))

;; Re-exported for legacy callers in other revops views that still
;; reference `revops-shell/sidebar-items`.
(def sidebar-items nav/admin-items)

;; Admin / RevOps dashboard — layout follows the "Painel admin" design.
;; Pulls live data from re-frame subs (apurações, sync status, contestações)
;; and falls back to the design's example values when subs are empty.

(defn- fmt-brl-int [v]
  (when v (str "R$ " (.toLocaleString (js/Math.round v) "pt-BR"))))

(defn- pct-bar [pct fill-class]
  [:div.bar
   [:div {:class (str "bar-fill " fill-class)
          :style {:width (str (min (or pct 0) 150) "%")}}]])

(defn- status->badge [status]
  (case status
    "REVIEWING"  [:span.badge.badge-review "Reviewing"]
    "VALIDATING" [:span.badge.badge-validating "Validating"]
    "LOCKED"     [:span.badge.badge-locked "Locked"]
    "DRAFT"      [:span.badge.badge-draft "Draft"]
    "APPROVED"   [:span.badge.badge-approved "Approved"]
    "CALCULATING"[:span.badge.badge-calc "Calculating"]
    [:span.badge.badge-locked (or status "—")]))

(defn- appraisal-row [{:keys [period status evs total]}]
  [:tr
   [:td.name.num period]
   [:td [status->badge status]]
   [:td.center.num (str (or evs "—"))]
   [:td.right.strong-num (or (fmt-brl-int total) "—")]
   [:td.right
    (case status
      "REVIEWING"  [:button.btn.btn-primary.btn-sm
                    {:on-click #(rf/dispatch [:navigate :revops/appraisal-review])}
                    "Revisar"]
      "VALIDATING" [:button.btn.btn-secondary.btn-sm "Acompanhar"]
      [:button.btn.btn-ghost.btn-sm "Ver"])]])

(defn- activity-item [{:keys [icon variant title when-text]}]
  [:div.activity-item
   [:div {:class (str "activity-dot" (when variant (str " " variant)))}
    [layout/icon icon {:width 11 :height 11}]]
   [:div.activity-content
    [:strong title]
    [:span.when when-text]]])

(defn revops-dashboard-page []
  (rf/dispatch [:revops/fetch-appraisals])
  (rf/dispatch [:revops/fetch-sync-status])
  (rf/dispatch [:revops/fetch-contestations])
  (fn []
    (let [appraisals    @(rf/subscribe [:revops/appraisals])
          sync-status   @(rf/subscribe [:revops/sync-status])
          contestations @(rf/subscribe [:revops/contestations])
          user          @(rf/subscribe [:auth/current-user])
          route         @(rf/subscribe [:current-route-name])
          active        (first (filter #(not= (:status %) "LOCKED") (or appraisals [])))
          contest-open  (count (filter #(= (:status %) "CONTESTED") (or contestations [])))
          recent-rows   (or (some->> appraisals
                                     (sort-by (juxt :year :quarter) #(compare %2 %1))
                                     (take 4)
                                     (map (fn [a]
                                            {:period (str "Q" (:quarter a) "/" (:year a))
                                             :status (:status a)
                                             :evs    (:ev_count a)
                                             :total  (:total_amount a)})))
                            [{:period "Q2/2026" :status "REVIEWING" :evs 14 :total 412300}
                             {:period "Q1/2026" :status "VALIDATING" :evs 14 :total 384110}
                             {:period "Q4/2025" :status "LOCKED" :evs 12 :total 356890}
                             {:period "Q3/2025" :status "LOCKED" :evs 11 :total 298420}])]
      [layout/page-shell
       {:current-route route :user user
        :crumbs ["plataforma rv" "admin" "dashboard"]
        :title "Painel admin"
        :subtitle "Visão geral do ciclo de comissões"
        :header-actions
        [[layout/search-input {:placeholder "Buscar…"}]
         [layout/icon-btn {:icon "bell" :dot? (pos? contest-open) :aria-label "Notificações"}]
         [:button.btn.btn-primary
          {:on-click #(rf/dispatch [:navigate :revops/appraisal])}
          [layout/icon "plus" {:width 14 :height 14}] "Nova apuração"]]}

       ;; Big status row
       [:div.kpi-grid.-three
        [:div.kpi
         [:div.kpi-label [layout/icon "cog" {:width 14 :height 14}] "apuração ativa"]
         [:div.kpi-value
          (if active
            [:<> "Q" (:quarter active) [:span.frac (str "/" (mod (or (:year active) 0) 100))]]
            "—")]
         [:div.kpi-foot
          (when active [status->badge (:status active)])
          [:span "etapa 3 de 6"]]
         [:svg.kpi-grafismo {:style {:color "var(--blue-light)"}} [:use {:href "#i-grafismo"}]]]
        [:div.kpi
         [:div.kpi-label [layout/icon "alert" {:width 14 :height 14}] "contestações pendentes"]
         [:div.kpi-value (str (if (pos? contest-open) contest-open 3))]
         [:div.kpi-foot
          [:span {:style {:color "var(--warning-dark)" :font-weight 600}} "Atenção"]
          " · 1 vence em 2 dias"]
         [:svg.kpi-grafismo {:style {:color "var(--warning-light)"}} [:use {:href "#i-grafismo-listras"}]]]
        [:div.kpi
         [:div.kpi-label [layout/icon "refresh" {:width 14 :height 14}] "último sync hubspot"]
         [:div.kpi-value {:style {:font-size "30px"}} (or (:last_sync sync-status) "há 12 min")]
         [:div.kpi-foot
          [:span.badge.badge-approved "OK"]
          [:span "1.842 negócios sincronizados"]]]]

       ;; Callout about active apuração
       (when active
         [:div.callout
          [layout/icon "info" {:width 20 :height 20}]
          [:div {:style {:flex 1}}
           [:strong (str "Apuração Q" (:quarter active) "/" (:year active) " está em revisão")]
           [:p {:style {:font-size "13px" :color "var(--fg-3)" :margin-top "2px"}}
            "Os cálculos foram concluídos. RevOps precisa validar os valores antes de enviar para os EVs."]]
          [:button.btn.btn-primary.btn-sm
           {:on-click #(rf/dispatch [:navigate :revops/appraisal-review])}
           "Revisar valores " [layout/icon "arrow-right" {:width 12 :height 12}]]])

       ;; Two col: appraisal list + activity
       [:div.two-col
        [:div.card {:style {:padding 0}}
         [:div {:style {:padding "24px 24px 16px" :display "flex" :justify-content "space-between" :align-items "center"}}
          [:div [:h3 "Apurações recentes"] [:div.card-sub "Últimos 4 ciclos"]]
          [:button.btn.btn-ghost.btn-sm
           {:on-click #(rf/dispatch [:navigate :revops/appraisal])}
           "Ver todas " [layout/icon "arrow-right" {:width 12 :height 12}]]]
         [:table.table
          [:thead
           [:tr
            [:th "Período"]
            [:th "Status"]
            [:th.center "EVs"]
            [:th.right "Total"]
            [:th.right "Ações"]]]
          [:tbody
           (for [row recent-rows]
             ^{:key (:period row)} [appraisal-row row])]]]

        [:div.card
         [:div.card-head
          [:div [:h3 "Atividade recente"] [:div.card-sub "Últimas 24h"]]]
         [:div.activity
          [activity-item {:icon "check" :variant "done"
                          :title "Sync HubSpot concluído"
                          :when-text "há 12 min · 1.842 negócios"}]
          [activity-item {:icon "cog" :variant "current"
                          :title "Cálculo Q2/2026 finalizado"
                          :when-text "há 1h · 14 EVs"}]
          [activity-item {:icon "msg"
                          :title "Nova contestação · Cliente A"
                          :when-text "há 2h · valor em disputa"}]
          [activity-item {:icon "upload"
                          :title "NF importada · Cliente B"
                          :when-text "há 5h · R$ 12.480"}]
          [activity-item {:icon "users"
                          :title "Usuário criado · Cliente F"
                          :when-text "ontem · perfil EV"}]]]]])))
