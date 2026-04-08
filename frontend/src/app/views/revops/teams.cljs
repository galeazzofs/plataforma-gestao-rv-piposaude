(ns app.views.revops.teams
  (:require [re-frame.core :as rf]
            [reagent.core :as r]
            [app.ds.layout :as layout]
            [app.ds.cards :as cards]
            [app.ds.table :as tbl]
            [app.ds.buttons :as btn]
            [app.ds.modal :as modal]
            [app.ds.inputs :as inputs]
            [app.ds.tokens :as t]
            [app.views.revops.dashboard :as revops-shell]
            [app.auth.subs]))

(defn empty-team-form [] {:name "" :leader_id ""})

(defn- team-form-from [team-data]
  (merge (empty-team-form)
         (select-keys (or team-data {}) [:name :leader_id])
         (when (:leader_id team-data) {:leader_id (str (:leader_id team-data))})))

(defn team-modal [{:keys [team-data]}]
  ;; Form-2: seed local form atom from props on mount; parent passes :key to remount
  (let [form (r/atom (team-form-from team-data))]
    (fn [{:keys [open? on-close team-data users]}]
      (let [editing? (some? (:id team-data))
            leader-options (into [{:value "" :label "Sem líder"}]
                                 (map #(hash-map :value (str (:id %)) :label (:name %))
                                      (filter #(= (:role %) "GERENTE") (or users []))))]
        [modal/modal {:open?    open?
                      :on-close on-close
                      :title    (if editing? "Editar Time" "Novo Time")
                      :size     :sm}
         [:div {:style {:display "flex" :flex-direction "column" :gap "16px"}}
          [inputs/input
           {:label     "Nome do Time"
            :value     (:name @form)
            :required  true
            :on-change #(swap! form assoc :name %)}]
          [inputs/select
           {:label     "Líder (Gerente)"
            :value     (or (:leader_id @form) "")
            :options   leader-options
            :on-change #(swap! form assoc :leader_id %)}]
          [:div {:style {:display "flex" :gap "10px" :justify-content "flex-end"}}
           [btn/button {:variant :secondary :on-click on-close} "Cancelar"]
           [btn/button
            {:variant  :primary
             :disabled (clojure.string/blank? (:name @form))
             :on-click (fn []
                         (let [payload (-> @form
                                           (update :leader_id
                                                   (fn [v] (when-not (clojure.string/blank? v) v))))]
                           (if editing?
                             (rf/dispatch [:revops/update-team (:id team-data) payload])
                             (rf/dispatch [:revops/create-team payload])))
                         (on-close))}
            (if editing? "Salvar" "Criar")]]]]))))

(defn members-modal [_]
  (let [picked (r/atom "")]
    (fn [{:keys [open? on-close team users]}]
      (let [team-id      (:id team)
            current-ids  (set (map :id (:members team)))
            available    (->> (or users [])
                              (filter (fn [u]
                                        (and (not (current-ids (:id u)))
                                             (#{"EV" "CN" "GERENTE"} (:role u))))))
            options      (into [{:value "" :label "Selecione um usuário…"}]
                               (map #(hash-map :value (:id %)
                                               :label (str (:name %) " — " (:role %)))
                                    available))]
        [modal/modal {:open?    open?
                      :on-close (fn [] (reset! picked "") (on-close))
                      :title    (str "Membros — " (:name team))
                      :size     :md}
         [:div {:style {:display "flex" :flex-direction "column" :gap "16px"}}
          [:div
           [:div {:style {:font-weight (:semibold t/font-weights)
                          :font-size   (:sm t/font-sizes)
                          :color       t/text-secondary
                          :margin-bottom "8px"}}
            "Membros atuais"]
           (if (empty? (:members team))
             [:div {:style {:padding "12px" :background t/beige-100
                            :border-radius (:md t/border-radius)
                            :color t/text-secondary :font-size (:sm t/font-sizes)}}
              "Nenhum membro neste time."]
             [:div {:style {:display "flex" :flex-direction "column" :gap "6px"}}
              (for [m (:members team)]
                ^{:key (:id m)}
                [:div {:style {:display "flex" :align-items "center" :justify-content "space-between"
                               :padding "8px 12px" :background t/beige-100
                               :border-radius (:md t/border-radius)}}
                 [:div
                  [:div {:style {:font-weight (:medium t/font-weights)}} (:name m)]
                  [:div {:style {:font-size (:xs t/font-sizes) :color t/text-secondary}}
                   (str (:role m) " · " (:email m))]]
                 [btn/button {:variant :ghost :size :sm
                              :on-click #(rf/dispatch
                                          [:revops/remove-team-member team-id (:id m)])}
                  "Remover"]])])]

          [:div
           [:div {:style {:font-weight (:semibold t/font-weights)
                          :font-size   (:sm t/font-sizes)
                          :color       t/text-secondary
                          :margin-bottom "8px"}}
            "Adicionar membro"]
           [:div {:style {:display "flex" :gap "8px" :align-items "flex-end"}}
            [:div {:style {:flex 1}}
             [inputs/select
              {:value     @picked
               :options   options
               :on-change #(reset! picked %)}]]
            [btn/button
             {:variant  :primary
              :disabled (clojure.string/blank? @picked)
              :on-click (fn []
                          (rf/dispatch [:revops/add-team-member team-id @picked])
                          (reset! picked ""))}
             "Adicionar"]]]

          [:div {:style {:display "flex" :justify-content "flex-end"}}
           [btn/button {:variant :secondary
                        :on-click (fn [] (reset! picked "") (on-close))}
            "Fechar"]]]]))))

(defn teams-page []
  (rf/dispatch [:revops/fetch-teams])
  (rf/dispatch [:revops/fetch-users])
  (let [modal-open?    (r/atom false)
        editing-team   (r/atom nil)
        members-open?  (r/atom false)
        members-team   (r/atom nil)
        confirm-open?  (r/atom false)
        confirm-row    (r/atom nil)
        team-columns [{:key :name        :label "Nome"       :sortable true}
                      {:key :leader_name :label "Líder"      :sortable false
                       :render (fn [row] (or (:leader_name row) "—"))}
                      {:key :members     :label "Membros"    :sortable false :align "center" :width "90px"
                       :render (fn [row]
                                 [:span {:style {:display "inline-flex" :align-items "center" :justify-content "center"
                                                 :width "28px" :height "28px" :border-radius (:full t/border-radius)
                                                 :background t/beige-100 :color t/beige-700
                                                 :font-size (:xs t/font-sizes) :font-weight (:bold t/font-weights)}}
                                  (str (count (or (:members row) [])))])}
                      {:key :actions     :label ""           :sortable false :width "220px"
                       :render (fn [row]
                                 [:div {:style {:display "flex" :gap "6px"}}
                                  [btn/button {:variant :ghost :size :sm
                                               :on-click #(do (reset! members-team row)
                                                              (reset! members-open? true))}
                                   "Membros"]
                                  [btn/button {:variant :ghost :size :sm
                                               :on-click #(do (reset! editing-team row)
                                                              (reset! modal-open? true))}
                                   "Editar"]
                                  [btn/button {:variant :danger :size :sm
                                               :on-click #(do (reset! confirm-row row)
                                                              (reset! confirm-open? true))}
                                   "Remover"]])}]]
    (fn []
      (let [teams    @(rf/subscribe [:revops/teams])
            users    @(rf/subscribe [:revops/users])
            loading? @(rf/subscribe [:revops/teams-loading?])
            user     @(rf/subscribe [:auth/current-user])
            route    @(rf/subscribe [:current-route-name])]
        [layout/page-shell
         {:sidebar-items revops-shell/sidebar-items
          :current-route route
          :user          user
          :title         "Times"
          :subtitle      "Gerenciar times e líderes"
          :header-actions
          [btn/button
           {:variant  :primary
            :on-click #(do (reset! editing-team nil)
                           (reset! modal-open? true))}
           "+ Novo Time"]}

         [cards/card {}
          [tbl/data-table
           {:columns       team-columns
            :rows          (or teams [])
            :empty-message (if loading? "Carregando..." "Nenhum time encontrado")}]]

         ^{:key (str "team-modal-" (or (:id @editing-team) "new") "-" @modal-open?)}
         [team-modal {:open?     @modal-open?
                       :on-close  #(reset! modal-open? false)
                       :team-data @editing-team
                       :users     users}]

         ;; Re-derive the team from the live `teams` list so that members refresh
         ;; in-place after add/remove without closing the modal.
         (let [live-team (some #(when (= (:id %) (:id @members-team)) %) (or teams []))]
           [members-modal {:open?    @members-open?
                           :on-close #(do (reset! members-open? false)
                                          (reset! members-team nil))
                           :team     (or live-team @members-team)
                           :users    users}])

         [modal/confirm-dialog
          {:open?         @confirm-open?
           :on-close      #(reset! confirm-open? false)
           :on-confirm    (fn []
                            (when-let [row @confirm-row]
                              (rf/dispatch [:revops/delete-team (:id row)]))
                            (reset! confirm-open? false))
           :title         "Confirmar remoção"
           :message       (str "Remover " (:name @confirm-row) "?")
           :confirm-label "Remover"
           :variant       :danger}]]))))
