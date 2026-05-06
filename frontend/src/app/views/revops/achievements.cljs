(ns app.views.revops.achievements
  (:require [reagent.core :as r]
            [re-frame.core :as rf]
            [app.ds.layout :as layout]
            [app.auth.subs]))

(defn- fmt-int [v]
  (when (some? v)
    (let [n (if (string? v) (js/parseFloat v) v)]
      (when-not (js/isNaN n) (.toLocaleString (js/Math.round n) "pt-BR")))))

(defn- fraction->pct-str [v]
  (when (some? v)
    (let [n (if (string? v) (js/parseFloat v) v)]
      (when-not (js/isNaN n) (.toFixed (* 100 n) 2)))))

(defn- pct-str->fraction [s]
  (let [n (js/parseFloat s)]
    (if (js/isNaN n) 0 (/ n 100.0))))

(defn- pct-bar [pct fill-class]
  [:div.bar
   [:div {:class (str "bar-fill " fill-class)
          :style {:width (str (min (or pct 0) 150) "%")}}]])

(defn- pct-class [pct]
  (cond (>= (or pct 0) 100) "success" (>= (or pct 0) 70) "warn" :else "danger"))

(defn- achievement-row [row edits filter-state]
  (let [ev-id (:ev_id row)
        stored (fraction->pct-str (:achievement_pct row))
        current (get @edits ev-id stored)
        pct-num (some-> current js/parseFloat)]
    [:tr
     [:td.name (:ev_name row)]
     [:td.right.strong-num (str "R$ " (or (fmt-int (:total_mrr row)) "·"))]
     [:td.right.strong-num (str "R$ " (or (fmt-int (:mrr_target row)) "·"))]
     [:td
      [:div.cell-progress
       [pct-bar pct-num (pct-class pct-num)]
       [:span.pct (str (or (some-> pct-num (.toFixed 0)) "·") "%")]]]
     [:td
      [:input.field-input
       {:type "number" :step "0.01" :min "0" :max "9999"
        :style {:width "120px" :padding "6px 10px"}
        :value (or current "")
        :on-change #(swap! edits assoc ev-id (.. % -target -value))}]]
     [:td.center (if (:is_final row)
                   [:span.badge.badge-paid "Final"]
                   [:span.badge.badge-locked "·"])]
     [:td.right
      (when (get @edits ev-id)
        [:button.btn.btn-primary.btn-sm
         {:on-click (fn []
                      (rf/dispatch
                        [:revops/save-achievement
                         {:ev_id ev-id
                          :quarter (:quarter @filter-state)
                          :year (:year @filter-state)
                          :achievement_pct (pct-str->fraction (get @edits ev-id))}])
                      (swap! edits dissoc ev-id))}
         "Salvar"])]]))

(defn achievements-page []
  (let [filter-state (r/atom {:quarter 2 :year 2026})
        edits (r/atom {})
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
         {:current-route route-name :user user
          :crumbs ["plataforma rv" "configuração" "atingimento"]
          :title "Atingimento por EV"
          :subtitle "Editar % de atingimento manual por trimestre"
          :header-actions
          [[:button.btn.btn-secondary
            {:on-click #(rf/dispatch [:revops/auto-calc-achievements @filter-state])}
            [layout/icon "refresh" {:width 14 :height 14}] "Auto-calcular baseline"]]}

         [:div.filter-row {:role "group" :aria-label "Filtrar por período"}
          (for [q [1 2 3 4]]
            ^{:key q}
            [:button {:type "button"
                      :class (str "chip" (when (= q (:quarter @filter-state)) " active"))
                      :aria-pressed (str (= q (:quarter @filter-state)))
                      :on-click #(on-filter-change :quarter q)}
             (str "Q" q)])
          [:div {:role "separator" :aria-hidden "true"
                 :style {:width "1px" :height "20px" :background "var(--border-subtle)" :margin "0 4px"}}]
          (for [y [2024 2025 2026 2027]]
            ^{:key y}
            [:button {:type "button"
                      :class (str "chip" (when (= y (:year @filter-state)) " active"))
                      :aria-pressed (str (= y (:year @filter-state)))
                      :on-click #(on-filter-change :year y)}
             (str y)])
          [:div {:style {:margin-left "auto" :font-family "var(--font-mono)" :font-size "11px"
                         :color "var(--fg-3)"}}
           "edite o % e clique em Salvar"]]

         [:div.card {:style {:padding 0}}
          [:table.table
           [:thead
            [:tr
             [:th "EV"]
             [:th.right "MRR Total"]
             [:th.right "Meta MRR"]
             [:th "Atingimento"]
             [:th "% Atingimento"]
             [:th.center "Final"]
             [:th.right "Ações"]]]
           [:tbody
            (cond
              loading?
              [:tr [:td {:col-span 7 :style {:padding "32px" :text-align "center" :color "var(--fg-3)"}}
                    "Carregando…"]]

              (empty? achievements)
              [:tr [:td {:col-span 7 :style {:padding "48px" :text-align "center" :color "var(--fg-3)"}}
                    "Nenhum EV ativo · cadastre EVs em Usuários"]]

              :else
              (for [row achievements]
                ^{:key (:ev_id row)}
                [achievement-row row edits filter-state]))]]]]))))
