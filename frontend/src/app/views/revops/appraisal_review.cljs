(ns app.views.revops.appraisal-review
  (:require [re-frame.core :as rf]
            [app.ds.layout :as layout]
            [app.ds.cards :as cards]
            [app.ds.table :as tbl]
            [app.ds.badge :as badge]
            [app.ds.buttons :as btn]
            [app.ds.tokens :as t]
            [app.views.revops.dashboard :as revops-shell]
            [app.auth.subs]))

(defn fmt-brl [v]
  (when v
    (str "R$ " (.toLocaleString v "pt-BR" #js {:minimumFractionDigits 2 :maximumFractionDigits 2}))))

(def review-columns
  [{:key :ev_name          :label "EV"            :sortable true}
   {:key :policies_count   :label "Negócios"      :sortable false}
   {:key :mrr_total        :label "MRR Total"     :sortable true
    :render (fn [row] (fmt-brl (:mrr_total row)))}
   {:key :commission_total :label "Comissão"      :sortable true
    :render (fn [row] (fmt-brl (:commission_total row)))}
   {:key :achievement_pct  :label "Atingimento"   :sortable true
    :render (fn [row]
              (let [pct (or (:achievement_pct row) 0)
                    color (cond (>= pct 100) t/success-default
                                (>= pct 50)  t/warning-default
                                :else        t/error-default)]
                [:span {:style {:color color :font-weight (:semibold t/font-weights)}}
                 (str (.toFixed pct 1) "%")]))}
   {:key :status           :label "Status"        :sortable false
    :render (fn [row] [badge/status-badge {:status (:status row)}])}])

(defn appraisal-review-page []
  (let [route-params (rf/subscribe [:current-route])]
    (fn []
      (let [appraisal-id (get-in @route-params [:path-params :id])
            _            (when appraisal-id (rf/dispatch [:revops/fetch-appraisal-detail appraisal-id]))
            appraisals   @(rf/subscribe [:revops/appraisals])
            appraisal    (first (filter #(= (str (:id %)) (str appraisal-id)) (or appraisals [])))
            ev-summary   (or (:ev_summary appraisal) [])
            loading?     @(rf/subscribe [:revops/appraisal-loading?])
            user         @(rf/subscribe [:auth/current-user])
            route        @(rf/subscribe [:current-route-name])]
        [layout/page-shell
         {:sidebar-items revops-shell/sidebar-items
          :current-route route
          :user          user
          :title         "Revisão de Apuração"
          :subtitle      (when appraisal (str "Q" (:quarter appraisal) "/" (:year appraisal)))
          :header-actions
          [:div {:style {:display "flex" :gap "8px"}}
           [btn/button {:variant  :secondary
                        :on-click #(rf/dispatch [:navigate! :revops/appraisal])}
            "← Voltar"]
           [btn/button {:variant  :primary
                        :on-click #(rf/dispatch [:revops/run-appraisal appraisal-id])}
            "Liberar para Validação EVs"]]}

         [cards/card {}
          [tbl/data-table
           {:columns       review-columns
            :rows          ev-summary
            :empty-message (if loading? "Carregando..." "Nenhum dado para revisão")}]]]))))
