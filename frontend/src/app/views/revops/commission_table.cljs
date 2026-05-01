(ns app.views.revops.commission-table
  (:require [reagent.core :as r]
            [re-frame.core :as rf]
            [app.ds.layout :as layout]
            [app.auth.subs]))

;; Tabela de comissão (rates) — matrix layout from the design.

(defn commission-table-page []
  (rf/dispatch [:revops/fetch-commission-table])
  (let [year (r/atom "2026")]
    (fn []
      (let [ct-data @(rf/subscribe [:revops/commission-table])
            ct-meta @(rf/subscribe [:revops/commission-table-meta])
            user    @(rf/subscribe [:auth/current-user])
            route   @(rf/subscribe [:current-route-name])
            ;; Group rows from API by segment and band, falling back to design data.
            multiplier-rows
            (or (some->> ct-data
                         (group-by :segment)
                         (map (fn [[seg rows]]
                                {:segment seg
                                 :bands   (->> rows (map (juxt :achievement_min :achievement_max :commission_pct)))}))
                         seq)
                [{:segment "EV Júnior" :bands [["0" "60" "0.0"] ["60" "80" "0.5"] ["80" "100" "1.0"]
                                                 ["100" "110" "1.15"] ["110" "120" "1.3"] ["120" "999" "1.5"]]}
                 {:segment "EV Pleno"  :bands [["0" "60" "0.0"] ["60" "80" "0.6"] ["80" "100" "1.0"]
                                                 ["100" "110" "1.2"] ["110" "120" "1.4"] ["120" "999" "1.6"]]}
                 {:segment "EV Sênior" :bands [["0" "60" "0.0"] ["60" "80" "0.7"] ["80" "100" "1.0"]
                                                 ["100" "110" "1.25"] ["110" "120" "1.5"] ["120" "999" "1.8"]]}
                 {:segment "CN"        :bands [["0" "60" "0.0"] ["60" "80" "0.5"] ["80" "100" "1.0"]
                                                 ["100" "110" "1.1"] ["110" "120" "1.2"] ["120" "999" "1.3"]]}])
            band-headers ["0–60%" "60–80%" "80–100%" "100–110%" "110–120%" "120%+"]]
        [layout/page-shell
         {:current-route route :user user
          :crumbs ["plataforma rv" "configuração" "tabela %"]
          :title "Tabela de comissão"
          :subtitle (str "Vigência " @year " · "
                         (if (:version ct-meta) (str "v" (:version ct-meta) " · ativa") "ativa"))
          :header-actions
          [[:button.btn.btn-secondary
            [layout/icon "eye" {:width 14 :height 14}] "Histórico"]
           [:button.btn.btn-primary
            {:on-click #(rf/dispatch [:revops/create-commission-version])}
            [layout/icon "edit" {:width 14 :height 14}] "Editar tabela"]]}

         [:div.filter-row
          (for [y ["2024" "2025" "2026"]]
            ^{:key y}
            [:div {:class (str "chip" (when (= y @year) " active"))
                   :on-click #(reset! year y)}
             y])]

         [:div.card
          [:div.card-head
           [:div [:h3 "Multiplicador por atingimento"]
            [:div.card-sub "× sobre comissão base, calculada por faixa de score"]]]
          [:table.matrix
           [:thead
            [:tr (into [[:th "Faixa"]] (for [h band-headers] [:th h]))]]
           [:tbody
            (for [{:keys [segment bands]} multiplier-rows]
              ^{:key segment}
              [:tr
               [:td segment]
               (for [[i [lo hi v]] (map-indexed vector bands)]
                 (let [;; Highlight the 100-110 band as "current" example
                       cur? (and (= segment "EV Júnior") (= "100" lo))]
                   ^{:key i}
                   [:td (when cur? {:class "cur"})
                    (str v "x")]))])]]]

         [:div.two-col-eq
          [:div.card
           [:div.card-head
            [:div [:h3 "% comissão base"]
             [:div.card-sub "Sobre MRR vendido"]]]
           [:table.matrix
            [:thead [:tr [:th "Operadora"] [:th "1ª parcela"] [:th "Recorrência"]]]
            [:tbody
             [:tr [:td "Operadora X"] [:td "5,0%"] [:td "1,5%"]]
             [:tr [:td "Operadora Y"] [:td "4,5%"] [:td "1,2%"]]
             [:tr [:td "Operadora Z"] [:td "5,5%"] [:td "1,8%"]]]]]
          [:div.card
           [:div.card-head
            [:div [:h3 "Pesos do score"]
             [:div.card-sub "Como compor atingimento final"]]]
           [:div {:style {:display "flex" :flex-direction "column" :gap "14px" :margin-top "4px"}}
            [:div
             [:div {:style {:display "flex" :justify-content "space-between" :margin-bottom "4px"}}
              [:span {:style {:font-family "var(--font-ui)" :font-size "13px" :font-weight 600}} "% SAO (R$)"]
              [:span {:style {:font-family "var(--font-mono)" :font-size "13px" :font-weight 600}} "60%"]]
             [:div.bar {:style {:height "8px"}}
              [:div.bar-fill {:style {:width "60%"}}]]]
            [:div
             [:div {:style {:display "flex" :justify-content "space-between" :margin-bottom "4px"}}
              [:span {:style {:font-family "var(--font-ui)" :font-size "13px" :font-weight 600}} "% Vidas"]
              [:span {:style {:font-family "var(--font-mono)" :font-size "13px" :font-weight 600}} "40%"]]
             [:div.bar {:style {:height "8px"}}
              [:div.bar-fill {:style {:width "40%" :background "var(--beige-light)"}}]]]]]]]))))
