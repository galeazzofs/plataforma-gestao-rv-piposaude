(ns app.views.revops.sync-status
  (:require [re-frame.core :as rf]
            [app.ds.layout :as layout]
            [app.auth.subs]))

;; Integrações / Sync — design's stacked sync cards.

(defn- sync-card [{:keys [name icon status badge-variant detail last-sync on? configurable?]}]
  [:div.sync-card
   [:div.sync-ico [layout/icon icon {:width 22 :height 22}]]
   [:div {:style {:flex 1 :display "flex" :flex-direction "column" :gap "2px"}}
    [:div {:style {:display "flex" :gap "10px" :align-items "center"}}
     [:strong {:style {:font-family "var(--font-heading)" :font-size "15px"
                       :font-weight 600 :color "var(--fg-1)"}}
      name]
     [:span {:class (str "badge badge-" (or badge-variant "approved"))} status]]
    [:div {:style {:font-size "13px" :color "var(--fg-3)"}} detail]
    [:div {:style {:font-family "var(--font-mono)" :font-size "11px" :color "var(--fg-3)"}}
     (str "último sync: " (or last-sync "—"))]]
   [:div {:style {:display "flex" :align-items "center" :gap "14px"}}
    [:div {:class (str "tog" (when on? " on"))}]
    (when configurable?
      [:button.btn.btn-secondary.btn-sm "Configurar"])]])

(defn sync-status-page []
  (rf/dispatch [:revops/fetch-sync-status])
  (fn []
    (let [status   @(rf/subscribe [:revops/sync-status])
          loading? @(rf/subscribe [:revops/sync-loading?])
          running? (:running status)
          user     @(rf/subscribe [:auth/current-user])
          route    @(rf/subscribe [:current-route-name])
          last-sync (or (:last_sync status) "há 12 min")
          synced-count (or (:records_synced status) "1.842")
          status-label (or (:status status) "OK")
          status-variant (case status-label
                           "OK"      "approved"
                           "RUNNING" "review"
                           "error")
          hubspot-detail (str (or synced-count "1.842") " negócios sincronizados")]
      [layout/page-shell
       {:current-route route :user user
        :crumbs ["plataforma rv" "operação" "sync"]
        :title "Integrações"
        :subtitle "HubSpot · Operadoras · Folha"
        :header-actions
        [[:button.btn.btn-primary
          {:disabled (or loading? running?)
           :on-click #(rf/dispatch [:revops/trigger-sync])}
          [layout/icon "refresh" {:width 14 :height 14}]
          (if running? "Sincronizando…" "Sincronizar agora")]]}

       (when running?
         [:div.callout {:style {:border-color "var(--warning-light)" :background "var(--warning-lightest)"}}
          [layout/icon "info" {:width 20 :height 20}]
          [:div {:style {:flex 1}}
           [:strong "Sincronização em andamento"]
           [:p {:style {:font-size "13px" :color "var(--fg-3)" :margin-top "2px"}}
            "Os dados serão atualizados automaticamente ao concluir."]]])

       [sync-card {:name "HubSpot" :icon "handshake"
                   :status status-label :badge-variant status-variant
                   :detail hubspot-detail :last-sync last-sync
                   :on? true :configurable? true}]
       [sync-card {:name "Operadora X" :icon "doc"
                   :status "OK" :badge-variant "approved"
                   :detail "312 apólices · 8.420 vidas" :last-sync "há 1h"
                   :on? true :configurable? true}]
       [sync-card {:name "Operadora Y" :icon "doc"
                   :status "OK" :badge-variant "approved"
                   :detail "198 apólices · 5.110 vidas" :last-sync "há 2h"
                   :on? true :configurable? true}]
       [sync-card {:name "Operadora Z" :icon "doc"
                   :status "Aguardando" :badge-variant "review"
                   :detail "API instável · retry em curso" :last-sync "há 8h"
                   :on? true :configurable? true}]
       [sync-card {:name "Folha · ADP" :icon "money"
                   :status "Pausado" :badge-variant "locked"
                   :detail "Reativar para liberar pagamentos" :last-sync "—"
                   :on? false :configurable? false}]

       (when (seq (:errors status))
         [:div.card
          [:h3 {:style {:color "var(--danger-dark)"}} "Erros recentes"]
          [:ul {:style {:margin "8px 0 0" :padding-left "20px"}}
           (for [e (:errors status)]
             ^{:key e} [:li {:style {:font-size "13px" :color "var(--danger-dark)"}} e])]])])))
