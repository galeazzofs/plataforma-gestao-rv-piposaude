(ns app.views.revops.sync-status
  (:require [re-frame.core :as rf]
            [app.ds.layout :as layout]
            [app.auth.subs]))

;; Integrações / Sync — mostra a integração HubSpot real (a única com sync
;; implementado no backend). Cards extras só aparecem quando o backend
;; expor outras integrações.

(defn- sync-card [{:keys [name icon status badge-variant detail last-sync]}]
  [:div.sync-card
   [:div.sync-ico [layout/icon icon {:width 22 :height 22}]]
   [:div {:style {:flex 1 :display "flex" :flex-direction "column" :gap "2px"}}
    [:div {:style {:display "flex" :gap "10px" :align-items "center"}}
     [:strong {:style {:font-family "var(--font-heading)" :font-size "15px"
                       :font-weight 600 :color "var(--fg-1)"}}
      name]
     (when status
       [:span {:class (str "badge badge-" (or badge-variant "approved"))} status])]
    (when detail [:div {:style {:font-size "13px" :color "var(--fg-3)"}} detail])
    (when last-sync
      [:div {:style {:font-family "var(--font-mono)" :font-size "11px" :color "var(--fg-3)"}}
       (str "último sync: " last-sync)])]])

(defn sync-status-page []
  (rf/dispatch [:revops/fetch-sync-status])
  (fn []
    (let [status   @(rf/subscribe [:revops/sync-status])
          loading? @(rf/subscribe [:revops/sync-loading?])
          running? (:running status)
          user     @(rf/subscribe [:auth/current-user])
          route    @(rf/subscribe [:current-route-name])
          last-sync (:last_sync status)
          synced-count (:records_synced status)
          status-label (:status status)
          status-variant (case status-label
                           "OK"      "approved"
                           "RUNNING" "review"
                           "ERROR"   "error"
                           "approved")
          hubspot-detail (when synced-count
                           (str (.toLocaleString synced-count "pt-BR")
                                " negócio" (when (not= 1 synced-count) "s")
                                " sincronizado" (when (not= 1 synced-count) "s")))]
      [layout/page-shell
       {:current-route route :user user
        :crumbs ["plataforma rv" "operação" "sync"]
        :title "Integrações"
        :subtitle "Sincronização de dados com sistemas externos"
        :header-actions
        [[:button.btn.btn-primary
          {:disabled (or loading? running?)
           :on-click #(rf/dispatch [:revops/trigger-sync])}
          [layout/icon "refresh" {:width 14 :height 14}]
          (if running? "Sincronizando…" "Sincronizar agora")]]}

       (when running?
         [:div.callout {:style {:border-color "var(--warning-light)"
                                :background "var(--warning-lightest)"}}
          [layout/icon "info" {:width 20 :height 20}]
          [:div {:style {:flex 1}}
           [:strong "Sincronização em andamento"]
           [:p {:style {:font-size "13px" :color "var(--fg-3)" :margin-top "2px"}}
            "Os dados serão atualizados automaticamente ao concluir."]]])

       (cond
         (and loading? (nil? status))
         [:div.card [:div {:style {:padding "32px" :text-align "center" :color "var(--fg-3)"}}
                     "Carregando…"]]

         (nil? status)
         [:div.card [:div {:style {:padding "48px" :text-align "center" :color "var(--fg-3)"}}
                     "Nenhuma integração configurada."]]

         :else
         [:<>
          [sync-card {:name "HubSpot" :icon "handshake"
                      :status status-label
                      :badge-variant status-variant
                      :detail hubspot-detail
                      :last-sync last-sync}]

          ;; Per-reason skip breakdown — useful when investigating why
          ;; fewer tickets came in than expected.
          (when-let [breakdown (some-> status :counts :skipped_breakdown)]
            (when (and (map? breakdown) (seq breakdown))
              [:div.card
               [:div.card-head
                [:div [:h3 "Skipped por motivo"]
                 [:div.card-sub "Tickets descartados na última sincronização"]]]
               [:div {:style {:display "flex" :gap "16px" :flex-wrap "wrap"}}
                (for [[k v] breakdown]
                  ^{:key k}
                  [:span.badge.badge-locked
                   (str (name k) ": " v)])]]))

          (when (seq (:errors status))
            [:div.card
             [:div.card-head
              [:div [:h3 {:style {:color "var(--danger-dark)"}} "Erros"]
               [:div.card-sub "Falhas reportadas durante a última sincronização"]]]
             [:ul {:style {:margin 0 :padding-left "20px"}}
              (for [e (:errors status)]
                ^{:key e}
                [:li {:style {:font-size "13px" :color "var(--danger-dark)" :margin-bottom "4px"}}
                 e])]])])])))
