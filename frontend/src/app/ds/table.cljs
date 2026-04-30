(ns app.ds.table
  (:require [app.ds.tokens :as t]
            [reagent.core :as r]))

(defn data-table
  "Data table with sort, pagination — restyled to match the .table spec from
   the Pipo design (mono uppercase headers, tight rows, hover highlight)."
  [{:keys [columns rows on-sort sort-key sort-order
           page total-pages on-page-change empty-message]}]
  [:div {:style {:border (str "1px solid " t/border-default)
                 :border-radius (:lg t/border-radius)
                 :overflow "hidden"
                 :background t/bg-card}}
   [:div {:style {:overflow-x "auto"}}
    [:table {:style {:width "100%" :border-collapse "collapse" :font-size "13px"}}
     [:thead
      [:tr
       (for [{:keys [key label sortable width align]} columns]
         ^{:key key}
         [:th {:style {:background t/bg-main
                       :border-bottom (str "1px solid " t/border-default)
                       :padding "11px 16px"
                       :text-align (or align "left")
                       :font-family t/font-mono
                       :font-size "10.5px"
                       :font-weight (:medium t/font-weights)
                       :color t/text-tertiary
                       :text-transform "uppercase"
                       :letter-spacing "0.06em"
                       :cursor (when sortable "pointer")
                       :width width
                       :white-space "nowrap"
                       :user-select "none"}
               :on-click (when (and sortable on-sort)
                           #(on-sort key))}
          [:span {:style {:display "inline-flex" :align-items "center" :gap "4px"}}
           label
           (cond
             (and sortable (= sort-key key))
             [:span {:style {:color t/text-primary}}
              (if (= sort-order :asc) " ↑" " ↓")]
             sortable
             [:span {:style {:color t/text-disabled :margin-left "2px"}} "↕"])]])]]
     [:tbody
      (if (empty? rows)
        [:tr [:td {:col-span (count columns)
                   :style {:padding "64px 16px" :text-align "center"}}
              [:div {:style {:display "flex" :flex-direction "column" :align-items "center" :gap "8px"
                             :color t/text-tertiary}}
               [:svg {:width 32 :height 32 :aria-hidden true
                      :style {:color t/border-hover}}
                [:use {:href "#i-list"}]]
               [:span {:style {:color t/text-tertiary :font-size "13px"}}
                (or empty-message "Nenhum dado encontrado")]]]]
        (map-indexed
         (fn [idx row]
           ^{:key (or (:id row) (hash row))}
           [(fn []
              (let [hovered? (r/atom false)]
                (fn []
                  [:tr {:style {:border-bottom (str "1px solid " t/border-default)
                                :background (if @hovered? t/bg-main t/bg-card)
                                :transition (str "background " t/transition-fast)}
                        :on-mouse-enter #(reset! hovered? true)
                        :on-mouse-leave #(reset! hovered? false)}
                   (for [{:keys [key render align]} columns]
                     ^{:key (str (or (:id row) idx) "-" key)}
                     [:td {:style {:padding "13px 16px"
                                   :color t/text-primary
                                   :font-family t/font-ui
                                   :text-align (or align "left")
                                   :vertical-align "middle"}}
                      (if render
                        (render row)
                        (get row key))])])))])
         rows))]]]
   (when (and page total-pages (> total-pages 1))
     [:div {:style {:display "flex" :justify-content "space-between" :align-items "center"
                    :padding "12px 16px"
                    :border-top (str "1px solid " t/border-default)
                    :background t/bg-card}}
      [:span {:style {:font-family t/font-mono :font-size "11px" :color t/text-tertiary}}
       (str "Página " page " de " total-pages)]
      [:div {:style {:display "flex" :gap "6px"}}
       [:button {:style {:padding "6px 11px"
                         :border (str "1px solid " t/border-default)
                         :border-radius (:sm t/border-radius)
                         :background t/bg-card
                         :font-family t/font-ui
                         :font-size "12px"
                         :font-weight (:semibold t/font-weights)
                         :cursor (if (> page 1) "pointer" "not-allowed")
                         :opacity (if (> page 1) "1" "0.4")}
                 :disabled (<= page 1)
                 :on-click #(when (> page 1) (on-page-change (dec page)))}
        "← Anterior"]
       [:button {:style {:padding "6px 11px"
                         :border (str "1px solid " t/border-default)
                         :border-radius (:sm t/border-radius)
                         :background t/bg-card
                         :font-family t/font-ui
                         :font-size "12px"
                         :font-weight (:semibold t/font-weights)
                         :cursor (if (< page total-pages) "pointer" "not-allowed")
                         :opacity (if (< page total-pages) "1" "0.4")}
                 :disabled (>= page total-pages)
                 :on-click #(when (< page total-pages) (on-page-change (inc page)))}
        "Próxima →"]]])])
