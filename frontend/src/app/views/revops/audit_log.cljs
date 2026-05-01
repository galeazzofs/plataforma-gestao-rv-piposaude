(ns app.views.revops.audit-log
  (:require [reagent.core :as r]
            [re-frame.core :as rf]
            [app.ds.layout :as layout]
            [app.auth.subs]))

;; Audit Log — mono row layout matching the design (.log-row).
;; Renders only events the API returned.

(defn- describe-action [{:keys [action table_name row_id changes]}]
  (let [t (or table_name "registro")
        a (case action
            "INSERT" "criou"
            "UPDATE" "atualizou"
            "DELETE" "removeu"
            (or action "alterou"))]
    (str a " " t
         (when row_id (str " · #" row_id))
         (when (and changes (seq changes))
           (str " · " (count changes) " alteraç" (if (= 1 (count changes)) "ão" "ões"))))))

(defn audit-log-page []
  (let [filters (r/atom {:from nil :to nil :table nil :user nil :search nil})
        fetch!  #(rf/dispatch [:revops/fetch-audit-log @filters])]
    (fetch!)
    (fn []
      (let [audit-log @(rf/subscribe [:revops/audit-log])
            loading?  @(rf/subscribe [:revops/audit-loading?])
            user      @(rf/subscribe [:auth/current-user])
            route     @(rf/subscribe [:current-route-name])
            items     (or (:items audit-log) [])
            meta      (:meta audit-log)
            total     (or (:total meta) (count items))]
        [layout/page-shell
         {:current-route route :user user
          :crumbs ["plataforma rv" "operação" "audit log"]
          :title "Audit Log"
          :subtitle "Imutável · todos os eventos do sistema"
          :header-actions
          [[:div.search
            [layout/icon "search" {:width 14 :height 14}]
            [:input {:placeholder "Filtrar por usuário, ação…"
                     :value (or (:search @filters) "")
                     :on-change (fn [e]
                                  (let [v (.. e -target -value)]
                                    (swap! filters assoc :search (when-not (= "" v) v))
                                    (fetch!)))}]]]}

         (when (pos? total)
           [:div.filter-row
            [:div {:style {:margin-left "auto" :font-family "var(--font-mono)" :font-size "11px"
                           :color "var(--fg-3)"}}
             (str total " evento" (when (not= 1 total) "s"))]])

         [:div.card {:style {:padding 0}}
          [:div.log-row {:style {:background "var(--bg-2)"
                                 :font-family "var(--font-mono)" :font-size "10px"
                                 :font-weight 600 :color "var(--fg-3)"
                                 :text-transform "uppercase"
                                 :letter-spacing "0.06em"}}
           [:div "timestamp"]
           [:div "ação"]
           [:div {:style {:text-align "right"}} "usuário"]]
          (cond
            loading?
            [:div {:style {:padding "32px" :text-align "center" :color "var(--fg-3)"}}
             "Carregando…"]

            (empty? items)
            [:div {:style {:padding "48px" :text-align "center" :color "var(--fg-3)"}}
             "Nenhum evento registrado"]

            :else
            (for [row items]
              ^{:key (or (:id row) (hash row))}
              [:div.log-row
               [:span.ts (or (:created_at row) (:timestamp row) "—")]
               [:span.what (or (:description row) (describe-action row))]
               [:span.who {:style {:text-align "right"}}
                (or (:user_name row) (:user_email row) "sistema")]]))]]))))
