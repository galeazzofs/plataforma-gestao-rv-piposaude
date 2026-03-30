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
  [:div {:style {:background t/bg-subtle
                 :border-radius (:md t/border-radius)
                 :padding "16px"
                 :text-align "center"}}
   [:div {:style {:font-size (:xs t/font-sizes) :color t/text-secondary :margin-bottom "4px"}} label]
   [:div {:style {:font-size (:xl t/font-sizes) :font-weight (:bold t/font-weights) :color t/color-primary}}
    (str value "%")]])

(defn commission-grid [rows]
  ;; rows from API: [{:segment "PME" :achievement_min "0" :achievement_max "100" :commission_pct "8.5"} ...]
  [:div {:style {:display "grid"
                 :grid-template-columns "repeat(3, 1fr)"
                 :gap "16px"}}
   (for [row (or rows [])]
     ^{:key (str (:segment row) (:achievement_min row) (:achievement_max row))}
     [grid-cell (str (:segment row) " (" (:achievement_min row) "–" (:achievement_max row) "%)") (:commission_pct row)])])

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
         "Criar nova versão"]}

       (when version
         [:div {:style {:margin-bottom "16px" :display "flex" :align-items "center" :gap "12px"}}
          [:span {:style {:color t/text-secondary :font-size (:sm t/font-sizes)}} "Versão atual:"]
          [badge/badge {:variant :success} (str "v" version)]
          [:span {:style {:color t/text-secondary :font-size (:xs t/font-sizes)}}
           (str "Efetiva desde " (or (:valid_from (first rows)) "—"))]])

       [cards/card {}
        (if loading?
          [:div {:style {:padding "48px" :text-align "center" :color t/text-secondary}} "Carregando..."]
          (if (empty? rows)
            [:div {:style {:padding "48px" :text-align "center" :color t/text-secondary}} "Nenhuma tabela encontrada"]
            [commission-grid rows]))]])))
