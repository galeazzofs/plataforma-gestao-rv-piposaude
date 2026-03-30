(ns app.views.revops.contestations
  (:require [re-frame.core :as rf]
            [reagent.core :as r]
            [app.ds.layout :as layout]
            [app.ds.cards :as cards]
            [app.ds.table :as tbl]
            [app.ds.badge :as badge]
            [app.ds.buttons :as btn]
            [app.ds.modal :as modal]
            [app.ds.inputs :as inputs]
            [app.ds.tokens :as t]
            [app.views.revops.dashboard :as revops-shell]
            [app.auth.subs]))

(defn resolve-modal [{:keys [open? on-close contestation]}]
  (let [resolution (r/atom "")]
    (fn []
      [modal/modal {:open?    open?
                    :on-close on-close
                    :title    "Resolver Contestação"
                    :size     :md}
       (when contestation
         [:div {:style {:display "flex" :flex-direction "column" :gap "16px"}}
          [:div {:style {:padding "12px" :background t/bg-subtle :border-radius (:md t/border-radius)}}
           [:span {:style {:font-size (:xs t/font-sizes) :color t/text-secondary}} "Comentário do EV:"]
           [:p {:style {:margin "4px 0 0" :font-size (:sm t/font-sizes)}}
            (or (:comment contestation) "—")]]
          [inputs/input
           {:label       "Resolução"
            :value       @resolution
            :placeholder "Descreva a resolução..."
            :on-change   #(reset! resolution %)
            :required    true}]
          [:div {:style {:display "flex" :gap "12px" :justify-content "flex-end"}}
           [btn/button {:variant :secondary :on-click on-close} "Cancelar"]
           [btn/button {:variant  :primary
                        :disabled (clojure.string/blank? @resolution)
                        :on-click (fn []
                                    (rf/dispatch [:revops/resolve-contestation (:id contestation) @resolution])
                                    (reset! resolution "")
                                    (on-close))}
            "Resolver"]]])])))

(def contestation-columns
  [{:key :ev_name     :label "EV"       :sortable true}
   {:key :client_name :label "Cliente"  :sortable false}
   {:key :created_at  :label "Data"     :sortable true}
   {:key :status      :label "Status"   :sortable false
    :render (fn [row] [badge/status-badge {:status (:status row)}])}
   {:key :comment     :label "Comentário" :sortable false
    :render (fn [row]
              [:span {:style {:max-width "200px" :display "block" :overflow "hidden"
                              :text-overflow "ellipsis" :white-space "nowrap"}}
               (or (:comment row) "—")])}
   {:key :actions     :label "Ações"    :sortable false}])

(defn contestations-page []
  (rf/dispatch [:revops/fetch-contestations])
  (let [modal-open?   (r/atom false)
        selected-cont (r/atom nil)]
    (fn []
      (let [contestations @(rf/subscribe [:revops/contestations])
            loading?      @(rf/subscribe [:revops/contestations-loading?])
            user          @(rf/subscribe [:auth/current-user])
            route         @(rf/subscribe [:current-route-name])
            action-cols
            (conj (vec (butlast contestation-columns))
                  {:key    :actions
                   :label  "Ações"
                   :render (fn [row]
                              (when (= (:status row) "CONTESTED")
                                [btn/button {:variant  :primary
                                             :size     :sm
                                             :on-click #(do (reset! selected-cont row)
                                                            (reset! modal-open? true))}
                                 "Resolver"]))})]
        [layout/page-shell
         {:sidebar-items revops-shell/sidebar-items
          :current-route route
          :user          user
          :title         "Contestações"
          :subtitle      "Revisar e resolver contestações dos EVs"}

         [cards/card {}
          [tbl/data-table
           {:columns       action-cols
            :rows          (or contestations [])
            :empty-message (if loading? "Carregando..." "Nenhuma contestação encontrada")}]]

         [@resolve-modal {:open?        @modal-open?
                          :on-close     #(reset! modal-open? false)
                          :contestation @selected-cont}]]))))
