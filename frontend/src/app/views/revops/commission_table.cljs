(ns app.views.revops.commission-table
  (:require [re-frame.core :as rf]
            [app.ds.layout :as layout]
            [app.ds.cards :as cards]
            [app.ds.buttons :as btn]
            [app.ds.badge :as badge]
            [app.ds.tokens :as t]
            [app.views.revops.dashboard :as revops-shell]
            [app.auth.subs]))

(defn grid-cell [label value]
  [:div {:style {:background t/bg-main
                 :border-radius (:lg t/border-radius)
                 :padding "20px"
                 :border (str "1px solid " t/border-default)
                 :display "flex"
                 :flex-direction "column"
                 :gap "8px"
                 :transition (str "all " t/transition-fast)}}
   [:div {:style {:font-size (:xs t/font-sizes) :color t/text-secondary
                  :text-transform "uppercase" :letter-spacing "0.06em"
                  :font-weight (:semibold t/font-weights)}} label]
   [:div {:style {:font-size (:2xl t/font-sizes) :font-weight (:bold t/font-weights) :color t/color-primary}}
    (str value "%")]])

(defn commission-grid [rows]
  ;; rows from API: [{:segment "PME" :achievement_min "0" :achievement_max "100" :commission_pct "8.5"} ...]
  [:div {:style {:display "grid"
                 :grid-template-columns "repeat(auto-fit, minmax(180px, 1fr))"
                 :gap "12px"}}
   (for [row (or rows [])]
     ^{:key (str (:segment row) (:achievement_min row) (:achievement_max row))}
     [grid-cell (str (:segment row) " · " (:achievement_min row) "–" (:achievement_max row) "%") (:commission_pct row)])])

(defn commission-table-page []
  (rf/dispatch [:revops/fetch-commission-table])
  (fn []
    (let [ct-data  @(rf/subscribe [:revops/commission-table])
          ct-meta  @(rf/subscribe [:revops/commission-table-meta])
          loading? @(rf/subscribe [:revops/commission-table-loading?])
          user     @(rf/subscribe [:auth/current-user])
          route    @(rf/subscribe [:current-route-name])
          version  (:version ct-meta)
          rows     (or ct-data [])]
      [layout/page-shell
       {:sidebar-items revops-shell/sidebar-items
        :current-route route
        :user          user
        :title         "Tabela de Comissões"
        :subtitle      "Percentuais por segmento e benefício"
        :header-actions
        [btn/button
         {:variant  :primary
          :on-click #(rf/dispatch [:revops/create-commission-version])}
         "+ Nova Versão"]}

       (when version
         [:div {:style {:display "flex" :align-items "center" :gap "10px"}}
          [:span {:style {:color t/text-secondary :font-size (:sm t/font-sizes)}} "Versão atual:"]
          [badge/badge {:variant :success} (str "v" version)]
          [:span {:style {:color t/text-secondary :font-size (:xs t/font-sizes)}}
           (str "Efetiva desde " (or (:valid_from (first rows)) "—"))]])

       [cards/card {}
        (if loading?
          [:div {:style {:padding "64px" :text-align "center"}}
           [:div {:style {:display "flex" :flex-direction "column" :align-items "center" :gap "8px"}}
            [:span {:style {:font-size "32px"}} "⏳"]
            [:span {:style {:color t/text-secondary}} "Carregando tabela..."]]]
          (if (empty? rows)
            [:div {:style {:padding "64px" :text-align "center"}}
             [:div {:style {:display "flex" :flex-direction "column" :align-items "center" :gap "8px"}}
              [:span {:style {:font-size "32px"}} "📊"]
              [:span {:style {:color t/text-secondary}} "Nenhuma tabela de comissões encontrada"]]]
            [commission-grid rows]))]])))
