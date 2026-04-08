(ns app.views.revops.achievements
  (:require [re-frame.core :as rf]
            [reagent.core :as r]
            [app.ds.layout :as layout]
            [app.ds.cards :as cards]
            [app.ds.table :as tbl]
            [app.ds.inputs :as inputs]
            [app.ds.buttons :as btn]
            [app.ds.tokens :as t]
            [app.views.revops.dashboard :as revops-shell]
            [app.auth.subs]))

(defn fmt-brl [v]
  (when (some? v)
    (let [n (if (string? v) (js/parseFloat v) v)]
      (when-not (js/isNaN n)
        (str "R$ " (.toLocaleString n "pt-BR"
                                    #js {:minimumFractionDigits 2
                                         :maximumFractionDigits 2}))))))

(defn- fraction->pct-str [v]
  (when (some? v)
    (let [n (if (string? v) (js/parseFloat v) v)]
      (when-not (js/isNaN n)
        (.toFixed (* 100 n) 2)))))

(defn- pct-str->fraction [s]
  (let [n (js/parseFloat s)]
    (if (js/isNaN n) 0 (/ n 100.0))))

(defn achievements-page []
  (let [filter-state (r/atom {:quarter 1 :year 2026})
        edits (r/atom {})  ; ev_id → pct as string ("75.50")
        on-filter-change
        (fn [k v]
          (swap! filter-state assoc k v)
          (reset! edits {})
          (rf/dispatch [:revops/fetch-achievements @filter-state]))]
    (rf/dispatch [:revops/fetch-achievements @filter-state])
    (fn []
      (let [user @(rf/subscribe [:auth/current-user])
            route-name @(rf/subscribe [:current-route-name])
            achievements (or @(rf/subscribe [:revops/achievements]) [])
            loading? @(rf/subscribe [:revops/achievements-loading?])]
        [layout/page-shell
         {:sidebar-items revops-shell/sidebar-items
          :current-route route-name
          :user user
          :title "Atingimento por EV"
          :subtitle "Editar % de atingimento manual por trimestre"
          :header-actions
          [btn/button
           {:variant :secondary
            :on-click #(rf/dispatch [:revops/auto-calc-achievements @filter-state])}
           "🤖 Auto-calcular baseline"]}

         [cards/card {}
          [:div {:style {:display "flex" :gap "12px" :margin-bottom "16px"
                         :align-items "flex-end"}}
           [:div {:style {:width "140px"}}
            [inputs/select
             {:label "Trimestre"
              :value (str (:quarter @filter-state))
              :options [{:value "1" :label "Q1"} {:value "2" :label "Q2"}
                        {:value "3" :label "Q3"} {:value "4" :label "Q4"}]
              :on-change #(on-filter-change :quarter (js/parseInt %))}]]
           [:div {:style {:width "140px"}}
            [inputs/select
             {:label "Ano"
              :value (str (:year @filter-state))
              :options [{:value "2024" :label "2024"}
                        {:value "2025" :label "2025"}
                        {:value "2026" :label "2026"}
                        {:value "2027" :label "2027"}]
              :on-change #(on-filter-change :year (js/parseInt %))}]]
           [:div {:style {:padding "0 12px" :color t/text-secondary
                          :font-size (:sm t/font-sizes)}}
            "💡 Edite o % e clique em Salvar pra cada EV"]]

          (if loading?
            [:div {:style {:padding "48px" :text-align "center"
                           :color t/text-secondary}}
             "Carregando..."]
            [tbl/data-table
             {:columns
              [{:key :ev_name :label "EV" :sortable true}
               {:key :total_mrr :label "MRR Total" :sortable false
                :render #(or (fmt-brl (:total_mrr %)) "—")}
               {:key :mrr_target :label "Meta MRR" :sortable false
                :render #(or (fmt-brl (:mrr_target %)) "—")}
               {:key :achievement_pct :label "% Atingimento" :sortable false
                :render
                (fn [row]
                  (let [ev-id (:ev_id row)
                        stored (fraction->pct-str (:achievement_pct row))
                        current (get @edits ev-id stored)]
                    [:input {:type "number" :step "0.01" :min "0" :max "9999"
                             :style {:width "110px" :padding "6px 8px"
                                     :border (str "1px solid " t/border-default)
                                     :border-radius (:md t/border-radius)
                                     :font-size (:sm t/font-sizes)}
                             :value (or current "")
                             :on-change #(swap! edits assoc ev-id
                                                (.. % -target -value))}]))}
               {:key :is_final :label "Final" :width "80px"
                :render #(if (:is_final %) "✅" "—")}
               {:key :actions :label "" :width "100px"
                :render
                (fn [row]
                  (let [ev-id (:ev_id row)
                        edited (get @edits ev-id)]
                    (when edited
                      [btn/button
                       {:variant :primary :size :sm
                        :on-click
                        #(do
                           (rf/dispatch
                            [:revops/save-achievement
                             {:ev_id ev-id
                              :quarter (:quarter @filter-state)
                              :year (:year @filter-state)
                              :achievement_pct (pct-str->fraction edited)}])
                           (swap! edits dissoc ev-id))}
                       "Salvar"])))}]
              :rows achievements
              :empty-message "Nenhum EV ativo. Cadastre EVs primeiro em Usuários."}])]]))))
