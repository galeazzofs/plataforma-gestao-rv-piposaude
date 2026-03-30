(ns app.views.revops.goals
  (:require [re-frame.core :as rf]
            [reagent.core :as r]
            [app.ds.layout :as layout]
            [app.ds.cards :as cards]
            [app.ds.table :as tbl]
            [app.ds.buttons :as btn]
            [app.ds.inputs :as inputs]
            [app.ds.tokens :as t]
            [app.views.revops.dashboard :as revops-shell]
            [app.auth.subs]))

(defn fmt-brl [v]
  (when v
    (str "R$ " (.toLocaleString v "pt-BR" #js {:minimumFractionDigits 2 :maximumFractionDigits 2}))))

(defn goal-row [{:keys [row on-edit]}]
  (let [editing? (r/atom false)
        value    (r/atom (or (:amount row) 0))]
    (fn []
      [:tr {:style {:border-bottom (str "1px solid " t/bg-subtle)}}
       [:td {:style {:padding "12px 16px"}} (:ev_name row)]
       [:td {:style {:padding "12px 16px"}} (str "Q" (:quarter row) "/" (:year row))]
       [:td {:style {:padding "12px 16px"}}
        (if @editing?
          [:input {:type      "number"
                   :value     @value
                   :style     {:padding "4px 8px" :border (str "1px solid " t/border-default)
                               :border-radius (:sm t/border-radius) :width "120px"}
                   :on-change #(reset! value (js/parseFloat (.. % -target -value)))}]
          (fmt-brl (:amount row)))]
       [:td {:style {:padding "12px 16px"}}
        (if @editing?
          [:div {:style {:display "flex" :gap "8px"}}
           [btn/button {:variant :primary :size :sm
                        :on-click (fn []
                                    (on-edit (:id row) {:amount @value})
                                    (reset! editing? false))}
            "Salvar"]
           [btn/button {:variant :secondary :size :sm
                        :on-click #(reset! editing? false)}
            "Cancelar"]]
          [btn/button {:variant :ghost :size :sm
                       :on-click #(reset! editing? true)}
           "Editar"])]])))

(defn goals-page []
  (rf/dispatch [:revops/fetch-goals])
  (fn []
    (let [goals    @(rf/subscribe [:revops/goals])
          loading? @(rf/subscribe [:revops/goals-loading?])
          user     @(rf/subscribe [:auth/current-user])
          route    @(rf/subscribe [:current-route-name])]
      [layout/page-shell
       {:sidebar-items revops-shell/sidebar-items
        :current-route route
        :user          user
        :title         "Metas"
        :subtitle      "Gerenciar metas por EV, trimestre e ano"
        :header-actions
        [:div {:style {:display "flex" :gap "8px"}}
         [inputs/file-upload
          {:label    "Importar XLSX"
           :accept   ".xlsx,.xls"
           :on-file  #(rf/dispatch [:revops/import-goals %])}]]}

       [cards/card {}
        (if loading?
          [:div {:style {:padding "48px" :text-align "center" :color t/text-secondary}} "Carregando..."]
          (if (empty? goals)
            [:div {:style {:padding "48px" :text-align "center" :color t/text-secondary}} "Nenhuma meta encontrada"]
            [:table {:style {:width "100%" :border-collapse "collapse" :font-size (:sm t/font-sizes)}}
             [:thead
              [:tr {:style {:border-bottom (str "2px solid " t/border-default)}}
               [:th {:style {:padding "12px 16px" :text-align "left" :color t/text-secondary
                             :font-size (:xs t/font-sizes) :text-transform "uppercase"}} "EV"]
               [:th {:style {:padding "12px 16px" :text-align "left" :color t/text-secondary
                             :font-size (:xs t/font-sizes) :text-transform "uppercase"}} "Período"]
               [:th {:style {:padding "12px 16px" :text-align "left" :color t/text-secondary
                             :font-size (:xs t/font-sizes) :text-transform "uppercase"}} "Valor (Meta)"]
               [:th {:style {:padding "12px 16px"}} ""]]]
             [:tbody
              (for [g (or goals [])]
                ^{:key (:id g)}
                [goal-row {:row g :on-edit (fn [id payload]
                                              (rf/dispatch [:revops/update-goal id payload]))}])]]))]])))
